# cosmos-monitor — Web Dashboard Eklentisi

Bu paket, mevcut `cosmos-monitor` reposuna **gerçek bir web paneli** ekler. TUI'deki
`chain.py` ve `fetcher.py` aynen kullanılır — veri çekme mantığında hiçbir tekrar
veya farklılık yoktur. Üzerine FastAPI tabanlı bir REST + WebSocket API ve
bağımsız bir HTML/CSS/JS arayüz eklenmiştir.

## İçerik

```
cosmos_monitor/cli.py          (değiştirildi — --web bayrağı eklendi)
pyproject.toml                 (değiştirildi — fastapi/uvicorn bağımlılığı eklendi)
cosmos_monitor/web/__init__.py (yeni)
cosmos_monitor/web/server.py   (yeni — FastAPI backend)
cosmos_monitor/web/static/*    (yeni — frontend: index.html, style.css, app.js)
```

## Kurulum

> **Not:** Daha önce bu paketi kurduysan ve `cosmos-monitor --web` çalışırken
> log'da sürekli `WARNING: No supported WebSocket library detected` görüyorsan,
> eski `pyproject.toml`'da `uvicorn` paketi WebSocket desteği olmadan
> kurulmuştu. Bu paketteki güncel `pyproject.toml`, `uvicorn[standard]`
> kullanıyor ve bunu otomatik çözüyor. Hızlı manuel çözüm (venv aktifken):
> `pip install websockets` — sonra `cosmos-monitor --web`'i yeniden başlat.

Sunucunda repoyu zaten klonladıysan, bu dosyaları aynı dizin yapısıyla üzerine
kopyala (yani `cosmos_monitor/cli.py` ve `pyproject.toml`'un üzerine yazılacak,
`cosmos_monitor/web/` klasörü yeni eklenecek):

```
# 1. Create a virtual environment specifically using Python 3.11
python3.11 -m venv venv

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Install your package safely (without sudo or --break-system-packages)
pip install -e .

OR

python3.11 -m pip install -e . --break-system-packages
```

```bash
cd ~/cosmos-monitor
pip install -e . --break-system-packages
```

Sıfırdan kuruyorsan, önce normal `install.sh` adımlarını uygula, sonra üstüne
bu paketi kopyala ve yine `pip install -e .` ile yeniden kur.

## Çalıştırma

```bash
cosmos-monitor --web
```

Varsayılan olarak `0.0.0.0:8000` üzerinde dinler (yani sunucunun her arayüzünden
erişilebilir). Tarayıcıdan `http://SUNUCU_IP:8000` adresine girince paneli görürsün.

Port veya host değiştirmek istersen:

```bash
cosmos-monitor --web --web-port 9000 --web-host 0.0.0.0 --refresh 5
```

Arka planda kalıcı çalışması için `systemd` servisi örneği:

```ini
# /etc/systemd/system/cosmos-monitor-web.service
[Unit]
Description=cosmos-monitor web dashboard
After=network.target

[Service]
ExecStart=/usr/local/bin/cosmos-monitor --web --web-port 8000
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cosmos-monitor-web
```

## Sunucu güvenlik duvarı

Bulut sağlayıcısının (AWS/GCP/Hetzner/DigitalOcean vb.) güvenlik grubunda veya
sunucudaki `ufw`'de ilgili portu açman gerekir:

```bash
sudo ufw allow 8000/tcp
```

## ÖNEMLİ — Güvenlik notu

Bu panelde **hiçbir kimlik doğrulama (login/şifre) yoktur**. Portu doğrudan
internete açık bırakırsan, validator node'larının IP'sini, peer sayısını,
komisyon ödüllerini ve hatta "node ekle/gizle" butonlarını herkes görüp
kullanabilir. Önerilen üç seçenekten birini uygula:

1. **En basit:** Güvenlik duvarında 8000 portunu sadece kendi IP adresine aç,
   herkese değil (`ufw allow from SENIN_IP to any port 8000`).
2. **SSH tüneli:** Portu hiç dışa açma, ihtiyaç olduğunda
   `ssh -L 8000:localhost:8000 kullanici@sunucu` ile tünelleyip
   `http://localhost:8000`'den bak.
3. **Nginx reverse proxy + Basic Auth:** Portu dışa açmadan önüne nginx koy,
   `htpasswd` ile kullanıcı adı/şifre ekle, HTTPS için Let's Encrypt kullan.
   İstersen bu kurulumu da ayrıca hazırlayabilirim.

## TUI'ye göre farklar / ek özellikler

- Üst barda tüm zincirleri tek bakışta gösteren küçük "yıldız" noktaları var
  (TUI'de sekmeler tek tek açılması gerekiyordu).
- Validator tablosunda arama kutusu ve sütun başlığına tıklayarak sıralama var.
- Aynı anda birden fazla kişi/sekme paneli izleyebilir (TUI tek terminal
  oturumuna bağlıydı).
- Klavye kısayolları aynen korundu: `r` yenile, `a` node ekle, `n`/`p` validator
  tablosunda sayfa değiştir (bir input/arama kutusuna yazarken devre dışı kalır).
