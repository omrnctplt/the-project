# Kurumsal Ortamlar için On-Premise AI Altyapısı
**GPU Time-Sharing Tabanlı, Kubernetes Orkestrasyon Sistemi**

Bu repository, bitirme projeniz kapsamında tasarlanan Rol Bazlı Yönlendirmeli AI Gateway ve Kubernetes (GPU Time-Sharing) altyapısının bir **Kavram Kanıtı (Proof of Concept - PoC)** sürümünü içerir.

## Proje Bileşenleri
1. **API Gateway (`api_gateway/`)**: Kullanıcı rollerine göre istekleri Büyük (GPU) veya Küçük (CPU) modele yönlendirir.
2. **Mock Modeller (`mock_models/`)**: Donanımsız ortamlarda sistemi test edebilmek için hazırlanmış sahte LLM sunucularıdır.
3. **Kubernetes Manifestoları (`kubernetes/manifests/`)**: Tüm sistemi konteynerleştirerek Kubernetes üzerinde çalıştırmaya yarayan yapılandırma dosyalarıdır.

---

## 🚀 GPU Time-Sharing Kurulum Rehberi (Gerçek Ortam İçin)

### Adım 1: NVIDIA Sürücüleri ve Container Toolkit'in Kurulumu
Fiziksel sunucunuzda NVIDIA ekran kartı sürücülerinin ve Docker'ın kurulu olduğundan emin olun. Daha sonra `nvidia-container-toolkit`'i kurun.

```bash
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Adım 2: NVIDIA Device Plugin Kurulumu (Time-Slicing Ayarı ile)
Kubernetes'in GPU'ları tanıması ve parçalara bölebilmesi için Time-Slicing ayarını yapmalıyız.

```yaml
# gpu-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: kube-system
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 10 # 1 fiziksel GPU'yu 10 sanal GPU olarak gösterir
```

Bu dosyayı Kubernetes'e uygulayın ve Device Plugin'i kurun:
```bash
kubectl apply -f gpu-config.yaml
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm install --generate-name nvdp/nvidia-device-plugin --namespace kube-system --set config.name=time-slicing-config
```

### Adım 3: Sistemlerin Çalıştırılması
Kendi modelinizi çalıştırırken Kubernetes YAML dosyanızda şu şekilde GPU talep edebilirsiniz:
```yaml
resources:
  limits:
    nvidia.com/gpu: "1" # Fiziksel GPU'nun 1/10'unu tahsis eder.
```