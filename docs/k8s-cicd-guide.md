# 基于 Kubernetes 的 CI/CD 流水线指南

## 核心概念澄清

Kubernetes 本身不是 CI/CD 工具，但它是 CI/CD 的**目标平台**。一个完整的 CI/CD 流程如下：

```
代码提交 → CI 引擎(构建/测试) → 镜像仓库 → K8s (CD 部署)
          ↑                      ↑
        GitHub Actions         Helm/Kustomize
        / Jenkins / GitLab CI
```

### K8s 在 CI/CD 中的角色

| 阶段 | K8s 的作用 | 工具 |
|------|-----------|------|
| **CI（持续集成）** | 无关，CI 在 Runner 上运行 | GitHub Actions / Jenkins |
| **CD（持续部署）** | 目标运行平台，接收新镜像 | Helm / Kustomize / ArgoCD |
| **CI 在 K8s 上运行** | Runner 本身跑在 K8s 上 | GitHub Actions Runner / Jenkins on K8s |

---

## 方案概览

| 方案 | 适合场景 | 复杂度 | 维护成本 |
|------|---------|--------|---------|
| **GitHub Actions + kubectl** | 轻量项目，当前 Yuxi 最匹配 | 低 | 低 |
| **GitHub Actions + Helm + ArgoCD** | 生产级 GitOps | 中 | 中 |
| **Jenkins on K8s** | 自建 CI/CD 平台 | 高 | 高 |
| **K8s 内运行 Runner (ARC)** | 大规模并发构建 | 中高 | 中 |

---

## 方案一：GitHub Actions + kubectl（推荐起步）

最适合 Yuxi 当前状态。CI 在 GitHub Actions 上运行，CD 通过 kubectl 或 Helm 推送到 K8s。

### 前置条件

1. 已在某个 K8s 集群上（kind / minikube / k3s / 云 K8s）
2. 项目有 Dockerfile（已存在 `docker/api.Dockerfile`）
3. GitHub 仓库已配置

### 1. 构建 K8s 部署清单

先创建 K8s 资源定义文件。

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: yuxi
```

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: yuxi-config
  namespace: yuxi
data:
  LITE_MODE: "true"
  VITE_USE_RUNS_API: "false"
  # 其他非敏感配置...
```

```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: yuxi-secrets
  namespace: yuxi
type: Opaque
stringData:
  # 使用 sealed-secrets 或 external-secrets 管理敏感数据
  # 这里仅作示例，生产环境不要明文提交
  DB_PASSWORD: "changeme"
  REDIS_PASSWORD: "changeme"
```

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: yuxi
  labels:
    app: api
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
      containers:
        - name: api
          image: ghcr.io/YOUR_ORG/yuxi/api:latest   # CI 会更新此 tag
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: yuxi-config
            - secretRef:
                name: yuxi-secrets
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "2"
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
```

```yaml
# k8s/api-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: yuxi
spec:
  selector:
    app: api
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```

```yaml
# k8s/web-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: yuxi
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
          image: ghcr.io/YOUR_ORG/yuxi/web:latest
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

```yaml
# k8s/web-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: yuxi
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 80
  type: ClusterIP
```

```yaml
# k8s/infra.yaml (PostgreSQL + Redis)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: yuxi
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:17-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: yuxi-secrets
                  key: DB_PASSWORD
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: yuxi
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: yuxi
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: yuxi
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: yuxi
spec:
  selector:
    app: redis
  ports:
    - port: 6372
      targetPort: 6379
```

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: yuxi-ingress
  namespace: yuxi
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
spec:
  rules:
    - host: yuxi.local   # 本地开发用，生产环境换真实域名
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
```

### 2. 配置 GitHub Actions CI/CD 流水线

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '*.md'
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAMESPACE: ${{ github.repository_owner }}

jobs:
  # ========== CI ==========
  test:
    name: Test & Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Backend
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Setup uv
        uses: astral-sh/setup-uv@v5

      - name: Install backend deps
        run: cd backend && uv sync

      - name: Run lint
        run: cd backend && uv run ruff check package

      - name: Run format check
        run: cd backend && uv run ruff format package --check

      - name: Run tests
        run: cd backend && uv run pytest -v

      # Frontend
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Setup pnpm
        uses: pnpm/action-setup@v4

      - name: Install frontend deps
        run: cd web && pnpm install

      - name: Run frontend lint
        run: cd web && pnpm run lint

  build-and-push:
    name: Build & Push Images
    runs-on: ubuntu-latest
    needs: test
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      # 提取 Git 信息
      - name: Get version tag
        id: version
        run: |
          SHA=$(git rev-parse --short HEAD)
          echo "sha=$SHA" >> $GITHUB_OUTPUT
          echo "tag=sha-$SHA" >> $GITHUB_OUTPUT

      # 登录镜像仓库
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # 构建 API 镜像
      - name: Build & Push API
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/api.Dockerfile
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/yuxi/api:${{ steps.version.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/yuxi/api:latest

      # 构建 Web 镜像
      - name: Build & Push Web
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/web.Dockerfile
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/yuxi/web:${{ steps.version.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/yuxi/web:latest

  # ========== CD ==========
  deploy:
    name: Deploy to K8s
    runs-on: ubuntu-latest
    needs: build-and-push
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Get version tag
        id: version
        run: echo "tag=sha-$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT

      # 配置 K8s 连接
      - name: Setup kubectl
        uses: azure/setup-kubectl@v4

      - name: Set Kubeconfig
        run: |
          mkdir -p $HOME/.kube
          echo "${{ secrets.KUBE_CONFIG }}" | base64 -d > $HOME/.kube/config

      # 更新镜像版本
      - name: Update image tags
        run: |
          sed -i "s|api:latest|api:${{ steps.version.outputs.tag }}|g" k8s/api-deployment.yaml
          sed -i "s|web:latest|web:${{ steps.version.outputs.tag }}|g" k8s/web-deployment.yaml

      # 部署到 K8s
      - name: Apply K8s manifests
        run: kubectl apply -f k8s/

      # 等待滚动更新完成
      - name: Wait for rollout
        run: |
          kubectl rollout status deployment/api -n yuxi --timeout=300s
          kubectl rollout status deployment/web -n yuxi --timeout=300s

      # 冒烟测试验证
      - name: Smoke test
        run: |
          # 等待 Pod 就绪后验证服务
          kubectl wait --for=condition=ready pod -l app=api -n yuxi --timeout=60s
          kubectl wait --for=condition=ready pod -l app=web -n yuxi --timeout=60s
          # 可以通过 Ingress 访问验证
          curl -f http://yuxi.local/health || echo "Health check endpoint not yet available"
```

### 3. 配置 GitHub Secrets

在 GitHub 仓库 Settings → Secrets → Actions 中添加：

| Secret | 说明 |
|--------|------|
| `KUBE_CONFIG` | K8s 集群的 kubeconfig 文件 (base64 编码) |

获取 KUBE_CONFIG 的方法：

```bash
# 本地 K8s (kind/minikube/k3s)
cat ~/.kube/config | base64 -w 0
# 输出粘贴到 GitHub Secrets

# 如果是云 K8s，从云控制台获取 kubeconfig 后同样 base64 编码
```

### 4. 本地测试流水线

```bash
# 先应用 K8s 配置
kubectl apply -f k8s/

# 本地构建并推送到本地 Docker 镜像
docker build -t yuxi/api:dev -f docker/api.Dockerfile .
docker build -t yuxi/web:dev -f docker/web.Dockerfile .

# 用本地镜像更新部署
kubectl set image deployment/api api=yuxi/api:dev -n yuxi
kubectl set image deployment/web web=yuxi/web:dev -n yuxi
```

---

## 方案二：ArgoCD GitOps（生产级推荐）

当项目成熟后，建议升级为 GitOps 模式：K8s 内运行 ArgoCD，自动同步 Git 仓库中 K8s 配置的变化。

```
GitHub Actions (CI) → 构建推送镜像 → 更新 Git 中的 image tag
                                                ↓
                                         ArgoCD (CD)
                                                ↓
                                         自动同步到 K8s
```

### 1. 安装 ArgoCD

```bash
# 安装 ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 等待安装完成
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s

# 获取初始密码
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### 2. 配置应用

```yaml
# k8s/argocd-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: yuxi
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/YOUR_ORG/yuxi.git
    targetRevision: main
    path: k8s/       # K8s 清单目录
  destination:
    server: https://kubernetes.default.svc
    namespace: yuxi
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

```bash
# 应用 ArgoCD 配置
kubectl apply -f k8s/argocd-app.yaml
```

### 3. 更新 CI 流水线（配合 ArgoCD）

ArgoCD 模式下 CD 步骤不再是 kubectl apply，而是通过 CI 更新 K8s 清单中的镜像 tag 并 push 到 Git：

```yaml
# .github/workflows/gitops-deploy.yml (新增 CD 部分)
  deploy:
    name: Update GitOps Manifest
    runs-on: ubuntu-latest
    needs: build-and-push
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Get version tag
        id: version
        run: echo "tag=sha-$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT

      # 更新 K8s 清单中的镜像 tag
      - name: Update manifests
        run: |
          sed -i "s|api:.*|api:${{ steps.version.outputs.tag }}|" k8s/api-deployment.yaml
          sed -i "s|web:.*|web:${{ steps.version.outputs.tag }}|" k8s/web-deployment.yaml

      # 提交并推送，ArgoCD 会自动检测到变更并部署
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add k8s/
          git commit -m "🚀 Deploy ${{ steps.version.outputs.tag }}" || echo "No changes"
          git push
```

---

## 方案三：Jenkins on K8s（自建 CI/CD 平台）

如果需要完全自建 CI/CD（如内网环境），可以在 K8s 上运行 Jenkins。

### 1. 部署 Jenkins

```bash
# 添加 Helm 仓库
helm repo add jenkins https://charts.jenkins.io
helm repo update

# 安装
helm install jenkins jenkins/jenkins \
  --namespace jenkins \
  --create-namespace \
  --set controller.serviceType=NodePort \
  --set controller.nodePort=30080 \
  --set agent.enabled=true

# 获取管理员密码
kubectl exec -n jenkins jenkins-0 -- cat /run/secrets/jenkins-admin-password
```

### 2. 创建 Jenkins Pipeline

```groovy
// Jenkinsfile
pipeline {
    agent any

    environment {
        REGISTRY = 'ghcr.io'
        IMAGE_NAMESPACE = 'your-org/yuxi'
    }

    stages {
        stage('Test') {
            parallel {
                stage('Backend Tests') {
                    steps {
                        sh '''
                        cd backend
                        uv run ruff check package
                        uv run pytest -v
                        '''
                    }
                }
                stage('Frontend Tests') {
                    steps {
                        sh '''
                        cd web
                        pnpm install
                        pnpm run lint
                        '''
                    }
                }
            }
        }

        stage('Build & Push') {
            steps {
                script {
                    docker.withRegistry("https://${env.REGISTRY}", 'ghcr-creds') {
                        def apiImage = docker.build("${env.REGISTRY}/${env.IMAGE_NAMESPACE}/api:${env.BUILD_NUMBER}", "-f docker/api.Dockerfile .")
                        apiImage.push()
                        apiImage.push("latest")

                        def webImage = docker.build("${env.REGISTRY}/${env.IMAGE_NAMESPACE}/web:${env.BUILD_NUMBER}", "-f docker/web.Dockerfile .")
                        webImage.push()
                        webImage.push("latest")
                    }
                }
            }
        }

        stage('Deploy to K8s') {
            steps {
                sh '''
                kubectl set image deployment/api api=$REGISTRY/$IMAGE_NAMESPACE/api:$BUILD_NUMBER -n yuxi
                kubectl set image deployment/web web=$REGISTRY/$IMAGE_NAMESPACE/web:$BUILD_NUMBER -n yuxi
                kubectl rollout status deployment/api -n yuxi --timeout=300s
                kubectl rollout status deployment/web -n yuxi --timeout=300s
                '''
            }
        }
    }
}
```

---

## 方案四：在 K8s 上运行 GitHub Actions Runner（ARC）

当构建频繁或需要本地 K8s 访问权限时，让 Runner 直接跑在 K8s 集群内。

```bash
# 安装 ARC (Actions Runner Controller)
helm install arc \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller \
  --namespace arc-systems \
  --create-namespace

# 配置 Runner Set
helm install arc-runner-set \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \
  --namespace arc-runners \
  --create-namespace \
  --set githubConfigUrl=https://github.com/YOUR_ORG/yuxi \
  --set githubConfigSecret.github_token=${{ secrets.RUNNER_TOKEN }}
```

配置完成后，CI 流水线中的 `runs-on: self-hosted` 会自动调度到 K8s 集群内的 Runner Pod 上。

---

## 流水线选择建议

| 阶段 | 推荐方案 | 理由 |
|------|---------|------|
| **开发验证** | 方案一 (Actions + kubectl) | 5 分钟内即可跑通，零额外组件 |
| **生产上线** | 方案二 (Actions + ArgoCD) | GitOps 标准模式，可追溯可回滚 |
| **内网/合规** | 方案三 (Jenkins on K8s) | 完全自建，不依赖外部服务 |
| **高频构建** | 方案四 (ARC) | Runner 在 K8s 内，减少网络开销 |

---

## 快速起步（5 分钟验证）

```bash
# 1. 起本地 K8s（选一个即可）
kind create cluster --name yuxi-dev
# 或
minikube start --driver=kvm2 --memory=8192

# 2. 部署应用
kubectl apply -f k8s/

# 3. 验证
kubectl get pods -n yuxi
kubectl get svc -n yuxi

# 4. 本地访问
kubectl port-forward svc/web -n yuxi 8080:80
# 浏览器打开 http://localhost:8080
```
