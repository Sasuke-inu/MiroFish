<template>
  <main id="workspace-content" tabindex="-1" class="missing-page">
    <span class="missing-mark" aria-hidden="true">≈</span>
    <p class="missing-code">404</p>
    <h1>{{ $t('quality.notFoundTitle') }}</h1>
    <p>{{ $t('quality.notFoundHelp') }}</p>
    <RouterLink to="/">{{ $t('quality.backHome') }} <span aria-hidden="true">→</span></RouterLink>
  </main>
</template>

<style scoped>
.missing-page { min-height: 100dvh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 18px; padding: 32px 24px; background: var(--studio-paper); }
.missing-mark { width: 52px; height: 52px; display: grid; place-items: center; background: var(--studio-button); color: #fff; border-radius: 14px; font-size: 38px; }
.missing-code { color: var(--studio-accent); letter-spacing: 4px; font-weight: 600; margin-top: 12px; }
h1 { font-size: clamp(26px, 4vw, 38px); }
p { color: var(--studio-muted); max-width: 460px; line-height: 1.8; }
a { margin-top: 12px; padding: 14px 22px; border-radius: 8px; background: var(--studio-button); color: #fff; text-decoration: none; display: flex; gap: 24px; }
</style>
