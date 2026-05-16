# 基于 MinIO 的 K8s 自动部署指南

## 架构概览

你期望的流程：

```
开发者上传软件包到 MinIO
        ↓
MinIO 检测到新文件 / 定时轮询发现变更
        ↓
触发 K8s Deployment 滚动更新
        ↓
Pod 重新启动，加载最新软件包
```

与传统的"构建镜像 → 推送仓库 → 更新 K8s"不同，这种方式把 **MinIO 作为软件包分发中心**，适合测试环境快速迭代。

---

## 目录结构

```
k8s/
├── namespace.yaml
├── minio-deploy-bucket-job.yaml    # 初始化部署专用 bucket
├── api-deployment.yaml             # API 部署（含 initContainer + 注解）
├── web-deployment.yaml
├── api-service.yaml
├── web-service.yaml
├── ingress.yaml
├── minio-watcher.yaml             # MinIO 事件监听器
└── deploy-script.sh               # 一键发包脚本
```

---

## 方案选择

| 方案 | 原理 | 延迟 | 复杂度 | 推荐场景 |
|------|------|------|--------|---------|
| **A. MinIO 事件通知 (Webhook)** | MinIO 推送事件到 Watcher → 触发重启 | 秒级 | 中 | 高频率发包 |
| **B. 轮询模式 (Polling)** | Watcher 定期检查 MinIO 文件 hash → 触发重启 | 分钟级 | 低 | 低频发包 |
| **C. 手动触发** | 上传后手动执行 kubectl rollout restart | 手动 | 最低 | 偶尔发包 |

**推荐：B 轮询模式**作为起步，无需额外配置 MinIO 服务端事件通知。

---

## 核心原理

```
┌─────────────────────────────────────────────────────────┐
│                    K8s Cluster                           │
│                                                          │
│  ┌──────────────────────┐    ┌───────────────────────┐  │
│  │  API Deployment       │    │  MinIO Watcher Pod     │  │
│  │                       │    │                        │  │
│  │ ┌───────────────────┐ │    │  ┌────────────────┐  │  │
│  │ │ InitContainer:     │ │    │  │ 每60s检查      │  │  │
│  │ │  从MinIO拉取包     │ │◄───┤│  MinIO文件状态  │  │  │
│  │ └───────────────────┘ │ │    │  发现新版本     │  │  │
│  │                       │ │    │    ↓             │  │  │
│  │ ┌───────────────────┐ │ │    │  Patch Deployment│  │  │
│  │ │ API Container      │ │ │    │  annotation     │  │  │
│  │ │ 运行应用           │ │ │    └────────────────┘  │  │
│  │ └───────────────────┘ │ │                          │  │
│  └──────────────────────┘ │                          │  │
└──────────────────────────────────────────────────────────┘
         │
         ▼ 外部访问
    用户/浏览器
         ▲
         │ 上传包
┌────────┴─────────┐
│   MinIO Server    │
│   :9000           │
│   Bucket: yuxi-   │
│   deployments     │
└──────────────────┘
```

---

## 一、创建 K8s 清单

### 1. Namespace

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: yuxi-test
```

### 2. API Deployment — InitContainer 拉取软件包

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: yuxi-test
  labels:
    app: api
  annotations:
    # 这个注解是 Watcher 触发滚动更新的关键
    yuxi.min.io/package-version: "initial"
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      # InitContainer: 从 MinIO 拉取最新软件包到共享卷
      initContainers:
        - name: fetch-package
          image: alpine:3.21
          command:
            - sh
            - -c
            - |
              set -e
              echo "Fetching latest package from MinIO..."
              # 安装 mc (MinIO Client)
              wget -q -O /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
              chmod +x /usr/local/bin/mc
              mc alias set yuxi-minio ${MINIO_URI} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY}
              # 拉取最新软件包
              mc cp --recursive yuxi-minio/yuxi-deployments/latest/ /app/package/
              echo "Package fetched successfully"
              # 记录版本信息
              mc stat yuxi-minio/yuxi-deployments/latest/VERSION 2>/dev/null && \
                mc cat yuxi-minio/yuxi-deployments/latest/VERSION > /app/package/.deployed-version || \
                echo "no-version" > /app/package/.deployed-version
              cat /app/package/.deployed-version
          env:
            - name: MINIO_URI
              value: "http://minio.yuxi-test.svc.cluster.local:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-creds
                  key: access-key
            - name: MINIO_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-creds
                  key: secret-key
          volumeMounts:
            - name: package-volume
              mountPath: /app/package

      containers:
        - name: api
          image: yuxi-api:0.6.0   # 基础镜像，代码通过共享卷覆盖
          ports:
            - containerPort: 5050
          command: ["uv", "run", "--no-dev", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "5050", "--reload"]
          envFrom:
            - configMapRef:
                name: yuxi-config
          env:
            - name: MINIO_URI
              value: "http://minio.yuxi-test.svc.cluster.local:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-creds
                  key: access-key
            - name: MINIO_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-creds
                  key: secret-key
          volumeMounts:
            - name: package-volume
              mountPath: /app/package
            - name: server-volume
              mountPath: /app/server
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "2"
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /api/system/health
              port: 5050
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/system/health
              port: 5050
            initialDelaySeconds: 5
            periodSeconds: 5

      volumes:
        # 使用 emptyDir 在 InitContainer 和主容器间共享
        - name: package-volume
          emptyDir: {}
        - name: server-volume
          emptyDir: {}

---
# MinIO 认证信息
apiVersion: v1
kind: Secret
metadata:
  name: minio-creds
  namespace: yuxi-test
type: Opaque
stringData:
  access-key: "minioadmin"
  secret-key: "minioadmin"
```

### 3. Web Deployment

```yaml
# k8s/web-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: yuxi-test
  labels:
    app: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: yuxi-web:0.6.0
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
```

### 4. Services

```yaml
# k8s/api-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: yuxi-test
spec:
  selector:
    app: api
  ports:
    - port: 5050
      targetPort: 5050
  type: ClusterIP
---
# k8s/web-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: yuxi-test
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 80
  type: ClusterIP
```

### 5. Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: yuxi-test-ingress
  namespace: yuxi-test
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
spec:
  rules:
    - host: yuxi-test.local
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 5050
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
```

### 6. MinIO Watcher（轮询模式）

```yaml
# k8s/minio-watcher.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio-watcher
  namespace: yuxi-test
  labels:
    app: minio-watcher
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio-watcher
  template:
    metadata:
      labels:
        app: minio-watcher
    spec:
      serviceAccountName: minio-watcher-sa
      containers:
        - name: watcher
          image: python:3.12-slim
          command: ["python", "/watcher/watcher.py"]
          env:
            - name: MINIO_URI
              value: "http://minio.yuxi-test.svc.cluster.local:9000"
            - name: MINIO_ACCESS_KEY
              value: "minioadmin"
            - name: MINIO_SECRET_KEY
              value: "minioadmin"
            - name: DEPLOY_BUCKET
              value: "yuxi-deployments"
            - name: DEPLOY_PREFIX
              value: "latest"
            - name: POLL_INTERVAL
              value: "30"
            - name: DEPLOYMENT_NAME
              value: "api"
            - name: DEPLOYMENT_NAMESPACE
              value: "yuxi-test"
          volumeMounts:
            - name: watcher-script
              mountPath: /watcher
      volumes:
        - name: watcher-script
          configMap:
            name: watcher-config
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: watcher-config
  namespace: yuxi-test
data:
  watcher.py: |
    """
    MinIO 轮询 Watcher
    定期检查 MinIO 上的软件包版本，发现新版本时触发 K8s Deployment 滚动更新。
    """
    import os
    import time
    import hashlib
    import json
    import subprocess
    import urllib.request
    import urllib.error
    from datetime import datetime

    MINIO_URI = os.getenv("MINIO_URI", "http://minio:9000")
    ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    BUCKET = os.getenv("DEPLOY_BUCKET", "yuxi-deployments")
    PREFIX = os.getenv("DEPLOY_PREFIX", "latest")
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
    DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "api")
    DEPLOYMENT_NS = os.getenv("DEPLOYMENT_NAMESPACE", "yuxi-test")
    STATE_FILE = "/tmp/.last-deploy-hash"

    def compute_minio_hash():
        """计算 MinIO 指定前缀下所有文件的组合 hash"""
        try:
            # 使用 mc 命令列出文件
            import subprocess
            result = subprocess.run(
                ["mc", "ls", "--recursive", f"yuxi-minio/{BUCKET}/{PREFIX}/"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                print(f"[WARN] mc ls failed: {result.stderr}")
                return None
            return hashlib.sha256(result.stdout.encode()).hexdigest()[:12]
        except Exception as e:
            print(f"[WARN] compute hash failed: {e}")
            return None

    def get_last_hash():
        try:
            with open(STATE_FILE) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def save_hash(h):
        with open(STATE_FILE, "w") as f:
            f.write(h)

    def trigger_rollout(new_hash):
        """通过 patch annotation 触发滚动更新"""
        timestamp = datetime.utcnow().isoformat()
        patch = json.dumps({
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "yuxi.min.io/last-deploy-hash": new_hash,
                            "yuxi.min.io/last-deploy-time": timestamp
                        }
                    }
                }
            }
        })
        try:
            result = subprocess.run(
                ["kubectl", "patch", "deployment", DEPLOYMENT_NAME,
                 "-n", DEPLOYMENT_NS, "--type", "merge", "-p", patch],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"[DEPLOY] Triggered rollout for {DEPLOYMENT_NAME} (hash={new_hash})")
            else:
                print(f"[ERROR] kubectl patch failed: {result.stderr}")
        except Exception as e:
            print(f"[ERROR] rollout failed: {e}")

    def setup_mc():
        """初始化 mc 客户端配置"""
        subprocess.run(
            ["mc", "alias", "set", "yuxi-minio", MINIO_URI, ACCESS_KEY, SECRET_KEY],
            capture_output=True
        )

    def main():
        print(f"[INIT] MinIO Watcher started")
        print(f"  URI: {MINIO_URI}")
        print(f"  Bucket: {BUCKET}/{PREFIX}")
        print(f"  Poll interval: {POLL_INTERVAL}s")
        print(f"  Target: {DEPLOYMENT_NS}/{DEPLOYMENT_NAME}")

        setup_mc()
        time.sleep(5)  # 等待 MinIO 就绪

        while True:
            current_hash = compute_minio_hash()
            if current_hash is None:
                print("[WARN] Failed to compute hash, retrying...")
                time.sleep(POLL_INTERVAL)
                continue

            last_hash = get_last_hash()
            print(f"[POLL] Current hash: {current_hash}, Last hash: {last_hash or 'none'}")

            if last_hash is None:
                print(f"[INIT] First run, recording hash: {current_hash}")
                save_hash(current_hash)
            elif current_hash != last_hash:
                print(f"[CHANGE] Detected new version! Triggering deploy...")
                trigger_rollout(current_hash)
                save_hash(current_hash)
            else:
                print(f"[OK] No changes detected")

            time.sleep(POLL_INTERVAL)

    if __name__ == "__main__":
        main()
---
# RBAC — 让 Watcher 有权限 patch Deployment
apiVersion: v1
kind: ServiceAccount
metadata:
  name: minio-watcher-sa
  namespace: yuxi-test
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: minio-watcher-role
  namespace: yuxi-test
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: minio-watcher-rolebinding
  namespace: yuxi-test
subjects:
  - kind: ServiceAccount
    name: minio-watcher-sa
    namespace: yuxi-test
roleRef:
  kind: Role
  name: minio-watcher-role
  apiGroup: rbac.authorization.k8s.io
```

---

## 二、MinIO Bucket 初始化

```yaml
# k8s/init-deploy-bucket.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: init-deploy-bucket
  namespace: yuxi-test
spec:
  template:
    spec:
      containers:
        - name: init-bucket
          image: minio/mc:latest
          command:
            - sh
            - -c
            - |
              mc alias set yuxi-minio http://minio.yuxi-test.svc.cluster.local:9000 minioadmin minioadmin
              mc mb yuxi-minio/yuxi-deployments 2>/dev/null || true
              echo "Bucket 'yuxi-deployments' ready"
      restartPolicy: OnFailure
  backoffLimit: 3
```

---

## 三、发包脚本

### 一键发包到测试环境

```bash
#!/usr/bin/env bash
# k8s/deploy-to-test.sh
# 用法: ./deploy-to-test.sh <软件包目录> [--no-wait]
# 示例: ./deploy-to-test.sh ./backend/package
# 示例: ./deploy-to-test.sh ./backend/package --no-wait

set -euo pipefail

MINIO_URI="${MINIO_URI:-http://localhost:9000}"
MC="mc"
BUCKET="yuxi-deployments"
DEPLOY_PREFIX="latest"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

if [ $# -lt 1 ]; then
    echo "用法: $0 <软件包目录>"
    echo "示例: $0 ./backend/package"
    exit 1
fi

PKG_DIR="$1"

if [ ! -d "$PKG_DIR" ]; then
    error "目录不存在: $PKG_DIR"
    exit 1
fi

# 检查 mc 客户端
if ! command -v "$MC" &>/dev/null; then
    info "安装 MinIO Client..."
    curl -fsSL -o /tmp/mc https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x /tmp/mc
    MC="/tmp/mc"
fi

# 配置 MinIO
$MC alias set yuxi-minio "$MINIO_URI" "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin}" 2>/dev/null || true

# 创建 bucket
$MC mb "yuxi-minio/$BUCKET" 2>/dev/null || true

info "清除旧的部署包..."
$MC rm --recursive --force "yuxi-minio/$BUCKET/$DEPLOY_PREFIX/" 2>/dev/null || true

info "上传软件包到 MinIO: $BUCKET/$DEPLOY_PREFIX/"
$MC cp --recursive "$PKG_DIR/" "yuxi-minio/$BUCKET/$DEPLOY_PREFIX/"

# 写入版本信息
VERSION="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "$VERSION" | $MC pipe "yuxi-minio/$BUCKET/$DEPLOY_PREFIX/VERSION"

info "部署版本: $VERSION"
info "软件包已上传至: $MINIO_URI/$BUCKET/$DEPLOY_PREFIX/"

# 如果是远程 K8s，手动触发 rollout（不依赖 Watcher）
if [ "${1:-}" = "--no-wait" ]; then
    info "已上传，Watcher 将自动检测并触发更新"
    exit 0
fi

# 直接触发滚动更新（跳过 Watcher 等待）
info "触发滚动更新..."
kubectl patch deployment api -n yuxi-test --type merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"yuxi.min.io/last-deploy-hash\":\"$VERSION\",\"yuxi.min.io/last-deploy-time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}}}}"

info "等待部署就绪..."
kubectl rollout status deployment/api -n yuxi-test --timeout=300s

info "✅ 部署完成！版本: $VERSION"
kubectl get pods -n yuxi-test -l app=api
```

### 本地快速发包（不经过 K8s）

如果你本地用 Docker Compose 开发，也可以用类似的脚本：

```bash
#!/usr/bin/env bash
# scripts/deploy-to-minio.sh
# 用法: ./scripts/deploy-to-minio.sh <目录>
# 直接上传到 MinIO，后端通过热重载自动生效

set -euo pipefail

PKG_DIR="${1:?用法: $0 <软件包目录>}"

echo "[INFO] 上传 $PKG_DIR 到 MinIO..."

# 使用 Python 脚本上传（利用项目已有的 MinIO 客户端）
python3 - << 'PYEOF'
import os, sys
from pathlib import Path

sys.path.insert(0, "backend")
from package.yuxi.storage.minio.client import get_minio_client

pkg_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PKG_DIR", "backend/package")
client = get_minio_client()
client.ensure_bucket_exists("yuxi-deployments")

upload_count = 0
for fpath in Path(pkg_dir).rglob("*"):
    if fpath.is_file() and not fpath.name.startswith("."):
        obj_name = f"latest/{fpath.relative_to(pkg_dir)}"
        data = fpath.read_bytes()
        client.upload_file("yuxi-deployments", obj_name, data)
        upload_count += 1
        print(f"  ↑ {obj_name}")

print(f"\n[OK] 上传 {upload_count} 个文件到 yuxi-deployments/latest/")
PYEOF

echo "[INFO] 触发 api 容器重启..."
docker restart api-dev

echo "[INFO] 等待服务就绪..."
sleep 10
curl -sf http://localhost:5050/api/system/health && echo "[OK] 服务健康" || echo "[WARN] 服务可能仍在启动"
```

---

## 四、方案 A：MinIO 事件通知（Webhook 模式）

如果你需要秒级响应的实时触发，可以配置 MinIO 的事件通知。

### 1. 配置 MinIO 事件通知

```bash
# 进入 MinIO 容器
docker exec -it minio sh

# 配置事件通知（指向 Watcher 服务）
mc admin config set yuxi-minio/ notify_webhook:deploy \
  enable=on \
  endpoint=http://minio-watcher.yuxi-test.svc.cluster.local:8080/webhook \
  queue_dir=/tmp/minio-webhook \
  queue_limit=10000

# 重启 MinIO 使配置生效
mc admin service restart yuxi-minio/

# 设置 bucket 事件
mc event add yuxi-minio/yuxi-deployments arn:minio:sqs::deploy:webhook \
  --event put --prefix latest/
```

### 2. 替换 Watcher 为事件驱动

```yaml
# k8s/minio-watcher-webhook.yaml (替代轮询版)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio-watcher
  namespace: yuxi-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio-watcher
  template:
    metadata:
      labels:
        app: minio-watcher
    spec:
      serviceAccountName: minio-watcher-sa
      containers:
        - name: watcher
          image: python:3.12-slim
          command: ["python", "/watcher/webhook_server.py"]
          ports:
            - containerPort: 8080
          env:
            - name: DEPLOYMENT_NAME
              value: "api"
            - name: DEPLOYMENT_NAMESPACE
              value: "yuxi-test"
          volumeMounts:
            - name: webhook-script
              mountPath: /watcher
      volumes:
        - name: webhook-script
          configMap:
            name: webhook-config
---
apiVersion: v1
kind: Service
metadata:
  name: minio-watcher
  namespace: yuxi-test
spec:
  selector:
    app: minio-watcher
  ports:
    - port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: webhook-config
  namespace: yuxi-test
data:
  webhook_server.py: |
    """
    MinIO Webhook 事件处理器
    接收 MinIO 的 s3:ObjectCreated 事件，触发 K8s Deployment 滚动更新。
    """
    import os
    import json
    import hashlib
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from datetime import datetime
    import subprocess

    DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "api")
    DEPLOYMENT_NS = os.getenv("DEPLOYMENT_NAMESPACE", "yuxi-test")

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                event = json.loads(body)
                # MinIO 事件格式
                records = event.get("Records", [])
                for record in records:
                    event_name = record.get("eventName", "")
                    obj_key = record.get("s3", {}).get("object", {}).get("key", "")

                    print(f"[WEBHOOK] {event_name}: {obj_key}")

                    if "ObjectCreated" in event_name:
                        self.trigger_deploy(obj_key)

                self.send_response(200)
                self.end_headers()
                self.write(b"OK")

            except Exception as e:
                print(f"[ERROR] {e}")
                self.send_response(500)
                self.end_headers()

        def trigger_deploy(self, object_key):
            timestamp = datetime.utcnow().isoformat()
            short_hash = hashlib.sha256(object_key.encode()).hexdigest()[:8]

            patch = json.dumps({
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "yuxi.min.io/last-deploy-hash": f"{short_hash}",
                                "yuxi.min.io/last-deploy-time": timestamp,
                                "yuxi.min.io/triggered-by": object_key
                            }
                        }
                    }
                }
            })

            result = subprocess.run(
                ["kubectl", "patch", "deployment", DEPLOYMENT_NAME,
                 "-n", DEPLOYMENT_NS, "--type", "merge", "-p", patch],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"[DEPLOY] Rollout triggered by: {object_key}")
            else:
                print(f"[ERROR] {result.stderr}")

        def log_message(self, format, *args):
            print(f"[HTTP] {format % args}")

    if __name__ == "__main__":
        print("[INIT] Webhook server starting on :8080")
        server = HTTPServer(("0.0.0.0", 8080), WebhookHandler)
        server.serve_forever()
```

---

## 五、部署流程（从零开始）

### Step 1: 创建 K8s 集群

```bash
# kind（最快）
kind create cluster --name yuxi-test

# 或 minikube
minikube start --driver=kvm2 --memory=8192 --name yuxi-test
```

### Step 2: 部署 MinIO（如果 K8s 内还没有）

```yaml
# k8s/minio-standalone.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: yuxi-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
        - name: minio
          image: minio/minio:latest
          command: ["minio", "server", "/data", "--address", "0.0.0.0:9000"]
          ports:
            - containerPort: 9000
            - containerPort: 9001
          env:
            - name: MINIO_ROOT_USER
              value: "minioadmin"
            - name: MINIO_ROOT_PASSWORD
              value: "minioadmin"
          volumeMounts:
            - name: minio-data
              mountPath: /data
      volumes:
        - name: minio-data
          persistentVolumeClaim:
            claimName: minio-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: minio
  namespace: yuxi-test
spec:
  selector:
    app: minio
  ports:
    - name: api
      port: 9000
      targetPort: 9000
    - name: console
      port: 9001
      targetPort: 9001
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-pvc
  namespace: yuxi-test
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
```

```bash
kubectl apply -f k8s/minio-standalone.yaml
```

### Step 3: 部署基础设施

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/init-deploy-bucket.yaml
kubectl wait --for=condition=complete job/init-deploy-bucket -n yuxi-test
```

### Step 4: 部署 Watcher

```bash
kubectl apply -f k8s/minio-watcher.yaml
kubectl wait --for=condition=available deployment/minio-watcher -n yuxi-test --timeout=120s
```

### Step 5: 部署应用

```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/web-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/web-service.yaml
kubectl apply -f k8s/ingress.yaml
```

### Step 6: 验证

```bash
kubectl get all -n yuxi-test
kubectl logs -f deployment/minio-watcher -n yuxi-test
```

---

## 六、日常发包操作

### 方式 1：脚本一键发包

```bash
# 将 backend/package 部署到测试环境
./k8s/deploy-to-test.sh ./backend/package
```

### 方式 2：手动上传 + 等待 Watcher

```bash
# 安装 mc
curl -fsSL -o /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x /usr/local/bin/mc

# 配置
mc alias set yuxi-minio http://localhost:9000 minioadmin minioadmin

# 上传
mc rm --recursive --force yuxi-minio/yuxi-deployments/latest/
mc cp --recursive ./backend/package/ yuxi-minio/yuxi-deployments/latest/

# Watcher 会在 30 秒内自动检测并触发更新
```

### 方式 3：直接触发（不上传，只重启）

```bash
kubectl rollout restart deployment/api -n yuxi-test
kubectl rollout status deployment/api -n yuxi-test --timeout=300s
```

---

## 七、监控与排障

```bash
# 查看 Watcher 日志
kubectl logs -f deployment/minio-watcher -n yuxi-test

# 查看 API 部署状态
kubectl describe deployment api -n yuxi-test

# 查看 Pod 日志
kubectl logs -l app=api -n yuxi-test --tail=50

# 查看当前部署版本
kubectl get deployment api -n yuxi-test -o jsonpath='{.spec.template.metadata.annotations}'

# 回滚到上一个版本
kubectl rollout undo deployment/api -n yuxi-test
```

---

## 八、进阶：打包成 Helm Chart

当上述流程稳定后，可以封装为 Helm Chart 方便复用：

```bash
helm create yuxi-test
# 将上述 K8s 清单替换 templates/ 中的内容
# values.yaml 中定义 minio、image、replicas 等参数
helm install yuxi-test ./yuxi-test -f values.yaml
```
