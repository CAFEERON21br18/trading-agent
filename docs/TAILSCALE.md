# Tailscale — accès distant privé au dashboard

Tailscale crée un réseau privé (VPN) entre tes appareils. La tour Windows, qui fait tourner le
dashboard AlphaSignal, et le téléphone rejoignent ce réseau. Tu ouvres alors le dashboard de
partout (4G, autre Wi-Fi), sans exposer la tour sur Internet. Gratuit pour un usage personnel.

Le dashboard n'écoute que sur `127.0.0.1` (`DASHBOARD_HOST`, défaut). Le seul accès depuis le
téléphone est Tailscale Serve, en HTTPS.

## Installation

1. **Compte** : https://tailscale.com → *Get started*.
2. **Tour Windows** : installer Tailscale depuis https://tailscale.com/download/windows, ouvrir
   l'application et se connecter au compte.
3. **Téléphone** : App Store ou Play Store → **Tailscale** → même compte.
4. **MagicDNS** : l'activer sur https://login.tailscale.com/admin/dns. La tour reçoit un nom
   `<machine>.<tailnet>.ts.net`.
5. **Exposer le dashboard sur le réseau privé**, depuis la racine du dépôt :
   ```powershell
   .venv\Scripts\python.exe scripts\setup_tailscale.py
   ```
   Le script configure Tailscale Serve (HTTPS 443 → `127.0.0.1:<DASHBOARD_PORT>`) et affiche
   l'adresse `https://<machine>.<tailnet>.ts.net/`. Il ne fait rien si le port est déjà servi.
   Si `tailscale.exe` n'est pas dans `C:\Program Files\Tailscale\`, donner son chemin dans
   `TAILSCALE_EXE_PATH` (`.env`).

Pour retirer l'exposition : `.venv\Scripts\python.exe scripts\teardown_tailscale.py`.

## Accès depuis le téléphone

Tailscale actif sur les deux appareils :

- ouvrir `https://<machine>.<tailnet>.ts.net/` dans Safari ou Chrome, puis « Sur l'écran d'accueil »
  (iPhone) ou « Installer l'application » (Android) ;
- `http://<ip>:8080` ne répond pas, ni par l'adresse Tailscale ni par celle du Wi-Fi : le dashboard
  n'écoute que sur `127.0.0.1`. `scripts/show_access_urls.py` affiche encore ces adresses : ne pas
  s'y fier ;
- aucun port de la box n'est ouvert.

## Sécurité

- Seuls les appareils connectés à ton compte Tailscale voient la tour.
- **Ne pas activer Tailscale Funnel** : c'est l'option qui exposerait le dashboard sur Internet.
  `setup_tailscale.py` n'appelle que `tailscale serve`.
- Le dashboard n'a pas d'authentification : ne pas repasser `DASHBOARD_HOST` à `0.0.0.0`.
- Les clés d'API restent dans `.env` sur la tour.

## Dépannage

| Problème | Piste |
|---|---|
| `setup_tailscale.py` : « Node Tailscale non connecté » | Ouvrir l'application Tailscale sur la tour, ou `tailscale up` |
| « DNSName introuvable » | MagicDNS n'est pas activé (`tailscale status`) |
| Le téléphone ne voit pas la tour | Tailscale actif des deux côtés ? Même compte ? |
| Le dashboard ne répond pas | La tour est en veille ou éteinte, ou le dashboard est arrêté : `logs\task_dashboard.log`, tâche `\AlphaSignal\dashboard` ; la tâche `surveillance` envoie un e-mail après 2 échecs |
