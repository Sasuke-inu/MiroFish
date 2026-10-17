"""R17: downloading a report must not leave un-cleaned temporary files behind."""
import os
import tempfile

import pytest
from flask import Flask

from app.api import report as api
from app.config import Config
from app.services.report_agent import Report, ReportManager, ReportStatus

CONTENT = 'SYNTHETIC_DOWNLOAD_BODY 合成下載內容\n第二行'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    app = Flask(__name__)
    app.register_blueprint(api.report_bp, url_prefix='/api/report')
    return app.test_client()


def test_download_serves_saved_text_without_temp_files(client, monkeypatch):
    ReportManager.save_report(Report(
        'report_dl', 'sim_dl', 'graph_dl', 'Fixture', ReportStatus.COMPLETED,
        created_at='2025-01-01', markdown_content=CONTENT))
    # Metadata exists but the full markdown file is gone: the fallback path answers.
    os.remove(ReportManager._get_report_markdown_path('report_dl'))

    calls = []

    def no_temp_file(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('temp file used for download')

    monkeypatch.setattr(tempfile, 'NamedTemporaryFile', no_temp_file)

    for _ in range(3):
        response = client.get('/api/report/report_dl/download')
        assert response.status_code == 200
        assert response.data == CONTENT.encode('utf-8')

    assert calls == []
    assert response.headers['Content-Disposition'].startswith('attachment')
    assert 'report_dl.md' in response.headers['Content-Disposition']
