"""Prove Chinese embeddings work from the cache with networking disabled."""
import asyncio
import json
import sys

import numpy as np

sys.path.insert(0, '/app/backend')
from app.local_graph.runtime import LocalEmbedder


async def main():
    embedder = LocalEmbedder()
    vectors = await embedder.create_batch(['社區咖啡店舉辦桌遊活動', '鄰里咖啡館的桌上遊戲聚會', '飛機引擎的維修手冊'])
    assert np.shape(vectors) == (3, 384)
    assert np.isfinite(vectors).all()
    related = float(np.dot(vectors[0], vectors[1]))
    unrelated = float(np.dot(vectors[0], vectors[2]))
    assert related > unrelated
    print(json.dumps({'network': 'disabled by Docker --network none', 'embedding_dimension': embedder.dimension,
                      'chinese_vectors': len(vectors), 'related_similarity': related,
                      'unrelated_similarity': unrelated, 'semantic_check': 'passed'}))


asyncio.run(main())
