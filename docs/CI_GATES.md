# CI 门禁

当前 GitHub OAuth 登录没有 `workflow` scope，因此仓库不直接提交 Actions workflow。
以下是与交付时完全相同的门禁；获得该 scope 后可原样放入 GitHub Actions。

## Backend / research contracts

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check backend/src scripts tests
pyright --pythonpath "$(command -v python)" backend/src scripts/research
python -m compileall -q backend/src scripts tests
bash -n scripts/bootstrap_server.sh scripts/server/run_training_matrix.sh \
  scripts/server/finalize_small_release.sh
```

## Frontend

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
```

服务器研究负载、数据和 GPU 测试仍只允许在运维手册指定的服务器路径运行。
