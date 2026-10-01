# Tailscale — accès distant sécurisé au dashboard

Tailscale crée un réseau privé (VPN) entre tes appareils. Le Mac (avec le
dashboard AlphaSignal) et le téléphone rejoignent ce réseau. Résultat :
tu peux ouvrir le dashboard depuis PARTOUT (4G, WiFi d'ami, hôtel…),
sans jamais exposer le Mac sur internet public. Gratuit pour un usage
personnel.

## Installation (~5 minutes)

### 1. Créer un compte
https://tailscale.com → *Get started* (connexion Google ou GitHub).

### 2. Installer sur le Mac
```bash
brew install --cask tailscale
```
Ou télécharger depuis https://tailscale.com/download/mac. Ouvrir l'app,
se connecter au compte créé.

### 3. Installer sur le téléphone
App Store / Play Store → **Tailscale** → même compte.

### 4. Activer MagicDNS (recommandé)
Sur https://login.tailscale.com/admin/dns → activer MagicDNS.
Le Mac devient accessible par son nom (ex: `ruby-mac.tailXXX.ts.net`)
au lieu d'une IP.

### 5. Vérifier
```bash
python3 scripts/show_access_urls.py
```
La ligne *Tailscale* doit maintenant apparaître avec ✅.

## Accès depuis le téléphone

Une fois Tailscale actif sur les 2 appareils (icône verte dans la
status bar) :

- **Partout** (4G, autre WiFi, WiFi maison) → ouvrir
  `https://<MAGIC_DNS_NAME>/` dans Safari / Chrome (Tailscale Serve,
  configuré par `scripts/setup_tailscale.py`).
- `http://<TAILSCALE_IP>:8080` et `http://<IP_LAN>:8080` ne répondent
  plus : le dashboard n'écoute que sur 127.0.0.1 (`DASHBOARD_HOST`).
- **Aucun port de la box n'est ouvert** — 100% privé, chiffré.

## Sécurité — ce qu'il faut savoir

- ✅ **Tailscale = réseau privé**. Seuls tes appareils connectés à
  ton compte peuvent voir le Mac.
- ❌ **Ne PAS activer *Tailscale Funnel*** — c'est l'option qui
  exposerait le dashboard sur internet public. On la laisse OFF.
- ✅ La clé API Gemini/Groq reste dans `.env` sur le Mac. Rien n'est
  poussé sur les serveurs Tailscale.

## HTTPS pour l'installation PWA

Chrome/Safari acceptent l'installation en HTTP pour `localhost` et
les IP privées (192.168.x, Tailscale 100.x). Si un jour l'installation
refuse en HTTP, activer HTTPS via :

```bash
# 1. Autoriser Tailscale à générer un cert
tailscale cert <MAGIC_DNS_NAME>

# 2. Utiliser tailscale serve pour proxy HTTPS → 8080
tailscale serve https / http://localhost:8080
```

Après ça, ouvrir `https://<MAGIC_DNS_NAME>` (sans port) sur le
téléphone → HTTPS valide, PWA installable partout.

## Dépannage

| Problème | Solution |
|---|---|
| `tailscale ip -4` vide | App Tailscale déconnectée → reconnecter |
| Téléphone ne voit pas le Mac | Tailscale actif ? (icône verte) Même compte ? |
| Dashboard timeout via Tailscale | Le Mac dort. `sudo pmset -a sleep 0` |
| PWA "Impossible d'installer" | Utiliser MagicDNS + `tailscale cert` (HTTPS) |
