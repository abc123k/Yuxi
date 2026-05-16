# Arch Linux 本地 Kubernetes 安装指南

## 本机配置

| 项目 | 配置 |
|------|------|
| OS | Arch Linux (rolling) |
| Kernel | 6.19.12-arch1-1 |
| CPU | 16 核心, x86_64 |
| 内存 | 64 GB (可用 54 GB) |
| 磁盘 | 根分区 49 GB, 剩余 26 GB |
| 虚拟化 | KVM 可用 (`/dev/kvm`) |
| 容器运行时 | Docker 29.4.0, Podman 5.8.2 |
| Init 系统 | systemd 260 |
| 网络 | wlan0 (192.168.31.75/24) |

## 方案选择

本机已安装 Docker 且 KVM 可用，资源充足。推荐以下两种方案：

| 方案 | 适用场景 | 资源占用 | 安装复杂度 |
|------|---------|---------|-----------|
| **kind** | 开发/测试，轻量快速 | 低 (~2GB) | 低 |
| **minikube + KVM** | 更接近生产，功能完整 | 中 (~4GB) | 中 |
| **k3s** | 轻量生产级，长期运行 | 低 (~1GB) | 低 |

---

## 方案一：kind (推荐开发测试)

kind (Kubernetes IN Docker) 将 K8s 节点运行为 Docker 容器，无需额外虚拟机。

### 1. 安装 kind 和 kubectl

```bash
# 安装 kubectl
pacman -S --noconfirm kubectl

# 安装 kind (通过 Go 或下载二进制)
# 方式 A: 使用 pacman (如果社区包可用)
pacman -S --noconfirm kind 2>/dev/null || {
  # 方式 B: 下载二进制
  curl -Lo /tmp/kind https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-amd64
  chmod +x /tmp/kind
  mv /tmp/kind /usr/local/bin/kind
}

# 验证
kubectl version --client
kind version
```

### 2. 创建集群

```bash
# 创建默认单节点集群
kind create cluster --name yuxi-dev

# 或创建多节点集群 (适合模拟生产)
cat > /tmp/kind-config.yaml << 'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
EOF

kind create cluster --name yuxi-dev --config /tmp/kind-config.yaml
```

### 3. 验证

```bash
kubectl cluster-info
kubectl get nodes
kubectl get pods -A
```

### 4. 安装 Ingress (多节点配置已包含端口映射)

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

### 5. 删除集群

```bash
kind delete cluster --name yuxi-dev
```

---

## 方案二：minikube + KVM2 驱动

利用本机 KVM 虚拟化，性能更好，更接近生产环境。

### 1. 安装依赖

```bash
# 安装 libvirt 和 virt-manager
pacman -S --noconfirm libvirt qemu vde2 dnsmasq bridge-utils openbsd-netcat

# 启动 libvirt
systemctl enable --now libvirtd

# 将当前用户加入 libvirt 组 (避免每次 sudo)
usermod -aG libvirt $(whoami)

# 注意: 需要重新登录或运行以下命令使组变更生效
newgrp libvirt

# 安装 minikube 和 kubectl
pacman -S --noconfirm minikube kubectl

# 验证
minikube version
kubectl version --client
```

### 2. 配置 libvirt 网络 (可选，如果需要外部访问)

```bash
# 检查默认网络是否活跃
virsh net-list --all

# 如果 default 网络未启动
virsh net-start default
virsh net-autostart default
```

### 3. 创建集群

```bash
# 使用 KVM2 驱动创建 (推荐 4 CPU + 8GB 内存，本机资源充足)
minikube start \
  --driver=kvm2 \
  --cpus=4 \
  --memory=8192 \
  --disk-size=20g \
  --cni=calico \
  --nodes=1 \
  --container-runtime=containerd

# 查看状态
minikube status
```

### 4. 安装 Ingress

```bash
minikube addons enable ingress
```

### 5. 常用命令

```bash
# 打开 Kubernetes Dashboard
minikube dashboard

# 获取服务 URL
minikube service <service-name> --url

# 暂停集群 (释放资源)
minikube pause

# 恢复集群
minikube unpause

# 停止集群
minikube stop

# 删除集群
minikube delete
```

---

## 方案三：k3s (轻量生产级)

k3s 是 CNCF 认证的轻量 K8s 发行版，适合作为长期运行的本地环境。

### 1. 安装 k3s

```bash
# 官方一键安装
curl -sfL https://get.k3s.io | sh -

# 禁用默认的 traefik (如果不需要)
curl -sfL https://get.k3s.io | sh -s - --disable traefik

# 如果只想用 Docker 作为容器运行时 (需要额外配置)
# 默认使用 containerd，推荐保持默认
```

### 2. 配置 kubectl

```bash
# k3s 会自动配置 kubeconfig
mkdir -p ~/.kube
cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
chmod 600 ~/.kube/config

# 或者设置 KUBECONFIG 环境变量
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
```

### 3. 验证

```bash
kubectl get nodes
kubectl get pods -A
```

### 4. 管理 k3s

```bash
# 停止
systemctl stop k3s

# 启动
systemctl start k3s

# 卸载
/usr/local/bin/k3s-uninstall.sh
```

---

## Helm 安装 (所有方案通用)

```bash
pacman -S --noconfirm helm
helm version
```

## 将 Yuxi 项目部署到 K8s 的后续步骤

1. **使用 kompose 转换 docker-compose.yml**:
   ```bash
   pacman -S --noconfirm kompose
   kompose convert -f docker-compose.yml
   ```

2. **或使用 Helm chart 管理部署** (推荐)

3. **配置持久化存储**: 本地可使用 hostPath 或 local-path-provisioner

---

## 常见问题

### 1. Docker 与 K8s 容器运行时冲突

kind 依赖 Docker，minikube/k3s 自带 containerd。如果同时运行，注意端口冲突：

```bash
# 检查端口占用
ss -tlnp | grep -E ':(6443|10250|2379|2380) '
```

### 2. 磁盘空间不足

根分区仅剩 26 GB，K8s 会占用较多空间。建议：

```bash
# 定期清理未使用的 Docker 镜像
docker system prune -a --volumes

# 清理 minikube 缓存
minikube cache delete --all

# 清理 k3s 旧镜像
crictl rmi --prune
```

### 3. Arch Linux 内核更新后 KVM 问题

```bash
# 确保 kvm 模块已加载
lsmod | grep kvm

# 手动加载
modprobe kvm_intel  # Intel CPU
modprobe kvm_amd    # AMD CPU
```

### 4. 网络问题

如果 K8s Pod 无法访问外网：

```bash
# 检查 CNI 配置
kubectl get pods -n kube-system | grep -E 'calico|flannel|cilium'

# kind 网络修复
docker network connect bridge $(kind get nodes --name yuxi-dev | head -1)
```

## 推荐选择

- **日常开发**: 方案一 (kind) — 启动快，与现有 Docker 环境兼容
- **功能测试**: 方案二 (minikube + KVM2) — 功能完整，可使用 Dashboard
- **长期运行**: 方案三 (k3s) — 资源占用最低，适合持续运行 Yuxi 项目
