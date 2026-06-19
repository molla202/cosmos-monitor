# cosmos-monitor — Web Dashboard Eklentisi

Bu paket, mevcut `cosmos-monitor` reposuna **gerçek bir web paneli** ekler. TUI'deki
`chain.py` ve `fetcher.py` aynen kullanılır — veri çekme mantığında hiçbir tekrar
veya farklılık yoktur. Üzerine FastAPI tabanlı bir REST + WebSocket API ve
bağımsız bir HTML/CSS/JS arayüz eklenmiştir.

## İçerik

```
cosmos_monitor/cli.py          (değiştirildi — --web bayrağı eklendi)
pyproject.toml                 (değiştirildi — fastapi/uvicorn[standard] bağımlılığı eklendi)
cosmos_monitor/web/__init__.py (yeni)
cosmos_monitor/web/server.py   (yeni — FastAPI backend)
cosmos_monitor/web/static/*    (yeni — frontend: index.html, style.css, app.js)
```

---

## 0) Python kurulumu (sıfırdan bir sunucuysa)

Sunucunda Python 3.11+ ve `venv` modülü yoksa önce bunları kur (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 --version          # 3.11+ olmalı
```

Ubuntu 22.04'te sistem Python'u 3.10 olabilir; `cosmos-monitor` 3.11+ ister.
3.11 yoksa:

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv
```

Bundan sonraki adımlarda `python3` yerine `python3.11` kullan.

---

## 1) cosmos-monitor'ı sanal ortamla kurma

```bash
cd ~
git clone https://github.com/molla202/cosmos-monitor.git
cd ~/cosmos-monitor

python3 -m venv venv
source venv/bin/activate          # bundan sonra prompt'un başında (venv) görünür
```

```bash
pip install --upgrade pip
pip install -e .
```

> **Not:** `pip install -e .` venv içindeyken `--break-system-packages` flag'ine
> gerek yok, o flag sadece venv kullanmadan doğrudan sistem Python'una kurarken
> gerekiyordu. `uvicorn[standard]` bağımlılığı sayesinde `websockets` kütüphanesi
> de otomatik kurulur — eskiden bu eksikti ve log'da
> `WARNING: No supported WebSocket library detected` hatası veriyordu. Hâlâ bu
> hatayı görüyorsan venv aktifken `pip install websockets` çalıştır ve servisi
> yeniden başlat.

---

## 2) Manuel çalıştırma (test için)

```bash
source ~/cosmos-monitor/venv/bin/activate
cosmos-monitor --web
```

`http://0.0.0.0:8000` üzerinde dinler, tarayıcıdan `http://SUNUCU_IP:8000` ile açarsın.
Port/host değiştirmek için: `cosmos-monitor --web --web-port 9000 --refresh 5`.

---

## 3) systemd servisi (sunucu yeniden başlasa da kalıcı çalışsın)

Servis dosyasını editör açmadan doğrudan `sudo tee` ile yazıyoruz. Aşağıdaki
komutu **tek parça halinde** kopyala-yapıştır (yollar `~/cosmos-monitor` ile
kurduğunu varsayıyor — kendi yolun farklıysa `ExecStart` ve `WorkingDirectory`
satırlarını güncelle):

```bash
sudo tee /etc/systemd/system/cosmos-monitor-web.service > /dev/null <<EOF
[Unit]
Description=cosmos-monitor web dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$HOME/cosmos-monitor
ExecStart=$HOME/cosmos-monitor/venv/bin/cosmos-monitor --web --web-host 0.0.0.0 --web-port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Servisi etkinleştir ve başlat:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cosmos-monitor-web
```

Durumunu ve loglarını kontrol et:

```bash
sudo systemctl status cosmos-monitor-web
sudo journalctl -u cosmos-monitor-web -f      # canlı log takibi, çıkmak için Ctrl+C
```

Servisi durdurmak/yeniden başlatmak için:

```bash
sudo systemctl restart cosmos-monitor-web
sudo systemctl stop cosmos-monitor-web
```

Kodda güncelleme yaptıktan sonra (yeni dosya kopyaladıysan) servisi yeniden
başlatman yeterli, `enable` tekrar gerekmez:

```bash
sudo systemctl restart cosmos-monitor-web
```

---

## 4) Sunucu güvenlik duvarı

Bulut sağlayıcısının (AWS/GCP/Hetzner/DigitalOcean vb.) güvenlik grubunda veya
sunucudaki `ufw`'de ilgili portu açman gerekir:

```bash
sudo ufw allow 8000/tcp
```


## TUI'ye göre farklar / ek özellikler

- Üst barda tüm zincirleri tek bakışta gösteren küçük "yıldız" noktaları var
  (TUI'de sekmeler tek tek açılması gerekiyordu).
- Validator tablosunda arama kutusu ve sütun başlığına tıklayarak sıralama var.
- Aynı anda birden fazla kişi/sekme paneli izleyebilir (TUI tek terminal
  oturumuna bağlıydı).
- Klavye kısayolları aynen korundu: `r` yenile, `a` node ekle, `n`/`p` validator
  tablosunda sayfa değiştir (bir input/arama kutusuna yazarken devre dışı kalır).
