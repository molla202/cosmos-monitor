# GitHub Repo Kurulum Rehberi

Bu dosya `cosmos-monitor` projesini GitHub'a yüklemek ve sunucuya kurmak için adım adım talimatları içerir.

---

## 1. GitHub'da Yeni Repo Oluştur

1. [github.com/new](https://github.com/new) adresine git
2. Şu bilgileri gir:
   - **Repository name:** `cosmos-monitor`
   - **Description:** `Multi-chain Cosmos validator TUI dashboard`
   - **Visibility:** Public ✓
   - **Add README:** HAYIR işaretle (bizim README.md'imiz var)
   - **Add .gitignore:** HAYIR
   - **License:** HAYIR (pyproject.toml'da MIT tanımlı)
3. **Create repository** butonuna bas
4. Açılan sayfadaki URL'yi not al: `https://github.com/KULLANICI_ADI/cosmos-monitor`

---

## 2. Lokal Bilgisayarda Git Başlat ve Push Et

Projeyi indirdiğin klasörde (cosmos-monitor/) şu komutları çalıştır:

```bash
cd cosmos-monitor

# Git başlat
git init

# Tüm dosyaları ekle
git add .

# İlk commit
git commit -m "feat: initial release - multi-chain Cosmos validator TUI"

# Ana branch adını main yap
git branch -M main

# GitHub reposunu remote olarak ekle (kendi kullanıcı adını yaz)
git remote add origin https://github.com/KULLANICI_ADI/cosmos-monitor.git

# Push et
git push -u origin main
```

> **Not:** GitHub kullanıcı adın ve şifren (veya Personal Access Token) sorulacak.
> Token oluşturmak için: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token
> Scope olarak sadece `repo` işaretle.

---

## 3. Release Tag Ekle (Opsiyonel ama Önerilen)

```bash
git tag -a v0.1.0 -m "cosmos-monitor v0.1.0 - initial release"
git push origin v0.1.0
```

GitHub'da Releases sayfasında görünür olur.

---

## 4. Sunucuya Kurulum

### Otomatik kurulum (tek komut):

```bash
bash <(curl -sSL https://raw.githubusercontent.com/KULLANICI_ADI/cosmos-monitor/main/install.sh)
```

### Manuel kurulum:

```bash
# Repoyu klonla
git clone https://github.com/KULLANICI_ADI/cosmos-monitor.git
cd cosmos-monitor

# Kur
pip3 install --break-system-packages -e .

# Veya
bash install.sh
```

### Güncelleme:

```bash
pip3 install --break-system-packages --upgrade \
    git+https://github.com/KULLANICI_ADI/cosmos-monitor.git
```

---

## 5. Sunucuda Kullanım

```bash
# Tüm chain'leri otomatik algıla
cosmos-monitor

# Belirli chain'leri izle
cosmos-monitor --home ~/.pchain --home ~/.lumera

# Algılanan chain'leri listele
cosmos-monitor --list

# Yardım
cosmos-monitor --help
```

---

## 6. tmux ile Arka Planda Çalıştırma (Önerilen)

```bash
# Yeni tmux session aç
tmux new-session -s monitor

# Dashboardı başlat
cosmos-monitor

# Detach et (dashboard çalışmaya devam eder)
# Ctrl+B → D

# Tekrar bağlan
tmux attach -t monitor
```

---

## 7. Sistem Servisi Olarak Kurmak (Opsiyonel)

Sunucu yeniden başladığında otomatik açılmasını istersen:

```bash
# Service dosyası oluştur
sudo tee /etc/systemd/system/cosmos-monitor.service > /dev/null << 'EOF'
[Unit]
Description=Cosmos Monitor TUI Dashboard
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
ExecStart=/usr/local/bin/cosmos-monitor
Restart=on-failure
RestartSec=5
Environment=TERM=xterm-256color

[Install]
WantedBy=multi-user.target
EOF

# Etkinleştir ve başlat
sudo systemctl daemon-reload
sudo systemctl enable cosmos-monitor
sudo systemctl start cosmos-monitor
```

---

## 8. Yeni Chain Ekleme

Yeni bir Cosmos chain desteklemek için `cosmos_monitor/chain.py` dosyasındaki `KNOWN_CHAINS` sözlüğüne şu şekilde ekle:

```python
KNOWN_CHAINS[".mychain"] = {
    "name":   "My Chain",
    "denom":  "MYC",
    "binary": "mychaind",
    "color":  "bright_yellow",
}
```

Sonra:

```bash
git add cosmos_monitor/chain.py
git commit -m "feat: add My Chain support"
git push
```

---

## 9. Logo Güncelleme

ANSI logoyu değiştirmek için:

```bash
# Yeni logoyu üret (jp2a, img2txt, vb. araçlarla)
# veya terminalde çiz ve output'u kaydet

# Mevcut logoyu değiştir
cp yeni_logo.ansi assets/logo.ansi

# Commit et
git add assets/logo.ansi
git commit -m "chore: update ANSI logo"
git push
```

---

## 10. Sorun Giderme

**`cosmos-monitor: command not found`**
```bash
# Python bin dizinini PATH'e ekle
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**`ModuleNotFoundError: No module named 'textual'`**
```bash
pip3 install --break-system-packages textual rich
```

**`Permission denied`**
```bash
# sudo olmadan pip kullan
pip3 install --user --break-system-packages \
    git+https://github.com/KULLANICI_ADI/cosmos-monitor.git
```

**RPC bağlantı hatası**
```bash
# Node'un çalıştığını kontrol et
cosmos-monitor --list

# Portu kontrol et (örnek: Push Chain için 54657)
curl http://localhost:54657/status | python3 -m json.tool
```
