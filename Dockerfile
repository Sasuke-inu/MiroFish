# Node 22 runtime is copied from the official image (multi-stage); Debian's apt nodejs is 18.x,
# below the frontend toolchain engines range (^22.22.2 || ^24.15.0 || >=26.0.0), so it is not usable here.
FROM node:22-bookworm-slim AS node

FROM python:3.11

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
  && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# 从 uv 官方镜像复制 uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# 先复制依赖描述文件以利用缓存
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY backend/pyproject.toml backend/uv.lock ./backend/
# uv.lock resolves camel-oasis from backend/vendor (pyproject [tool.uv.sources] path dependency),
# so vendor/ must be present before any uv sync; --no-install-project keeps this layer cacheable.
COPY backend/vendor/ ./backend/vendor/

# 安装依赖（Node + Python；此时不安装 backend 项目本身）
RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync --frozen --no-install-project

# 复制项目源码
COPY . .

# 项目源码就绪后再安装 backend 项目本身
RUN cd backend && uv sync --frozen

EXPOSE 3000 5001

# 同时启动前后端（开发模式）
CMD ["npm", "run", "dev"]
