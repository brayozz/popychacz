# patchbot-bridge

Mały mostek: nasłuchuje na jednym kanale Discorda (tym, na który PatchBot
wysyła powiadomienia) i każdą wiadomość przekazuje na Slacka przez
Incoming Webhook.

Zaprojektowany pod: Debian 12, kontener LXC, 1 GB RAM. Zużycie w spoczynku
to zwykle 50–80 MB RAM, więc limit `MemoryMax=200M` w usłudze systemd jest
wygodnym marginesem bezpieczeństwa.

---

## 1. Kontener LXC

Jeśli jeszcze go nie masz, na hoście:

```bash
lxc-create -n patchbridge -t debian -- -r bookworm
lxc-start -n patchbridge
lxc-attach -n patchbridge
```

W kontenerze:

```bash
apt update && apt install -y python3 python3-venv python3-pip
```

## 2. Discord — utworzenie bota (krok po kroku)

### 2.1 Załóż aplikację

1. Wejdź na **https://discord.com/developers/applications** i zaloguj się
   (tym samym kontem, którym korzystasz z Discorda normalnie).
2. W prawym górnym rogu kliknij niebieski przycisk **New Application**.
3. Pojawi się okienko z polem na nazwę — wpisz np. `PatchBot Bridge`
   (to tylko nazwa techniczna, użytkownicy jej raczej nie zobaczą inaczej
   niż jako nazwę bota na serwerze), zaakceptuj regulamin i kliknij **Create**.
4. Zostaniesz przeniesiony na stronę **General Information** tej aplikacji.
   To jest "centrum dowodzenia" — po lewej stronie masz pionowe menu
   (General Information, OAuth2, Bot, itd.). Tego menu będziemy używać
   w kolejnych krokach.

### 2.2 Zamień aplikację w bota i zdobądź token

1. W lewym menu kliknij **Bot**.
2. Na tej stronie od razu widzisz, że bot już istnieje (Discord tworzy go
   automatycznie razem z aplikacją) — zobaczysz jego nazwę i ikonę.
3. Znajdź sekcję z napisem **Token**. Jeśli token nie jest jeszcze widoczny,
   kliknij **Reset Token** (potwierdź, jeśli Discord poprosi o hasło/2FA) —
   token pokaże się tylko raz, więc od razu kliknij **Copy**.
4. Wklej ten token do pliku `.env` jako wartość `DISCORD_TOKEN`
   (patrz sekcja 4 niżej). **Nikomu go nie pokazuj i nie wrzucaj do Gita** —
   kto ma token, ten w pełni kontroluje bota.
5. Na tej samej stronie **Bot**, przewiń niżej do sekcji
   **Privileged Gateway Intents**. Zobaczysz tam trzy przełączniki:
   `PRESENCE INTENT`, `SERVER MEMBERS INTENT`, `MESSAGE CONTENT INTENT`.
   Włącz (kliknij, żeby zrobił się zielony/aktywny) **wyłącznie**
   **MESSAGE CONTENT INTENT** — pozostałych dwóch nie potrzebujemy.
   Bez tego przełącznika bot owszem "zobaczy", że przyszła wiadomość,
   ale pole z jej treścią i embedami będzie puste.
6. Na dole strony kliknij **Save Changes** (Discord czasem pokazuje ten
   przycisk dopiero po najechaniu na dół strony — jeśli nie widzisz zmiany,
   odśwież stronę i sprawdź, czy przełącznik faktycznie został zapisany).

### 2.3 Zbuduj link zapraszający bota na serwer

1. W lewym menu kliknij **OAuth2**, a potem w tej samej sekcji znajdź
   podstronę **URL Generator** (na niektórych układach to zakładka/sekcja
   na tej samej stronie OAuth2, przewiń jeśli nie widzisz od razu).
2. W sekcji **Scopes** zaznacz checkbox **bot** (nic więcej, nie zaznaczaj
   `applications.commands` — nie potrzebujemy komend slash).
3. Po zaznaczeniu `bot` pod spodem pojawi się nowa sekcja
   **Bot Permissions**. Zaznacz tam tylko:
   - **View Channel**
   - **Read Message History**
   
   Nie zaznaczaj niczego więcej (bot nie musi pisać ani zarządzać serwerem).
4. Na samym dole strony pojawi się wygenerowany **URL** — kliknij **Copy**.
5. Wklej ten URL w nowej karcie przeglądarki i wciśnij Enter.
6. Discord pokaże ekran wyboru serwera — z rozwijanej listy **Add to Server**
   wybierz swój serwer (ten, na którym jest kanał z PatchBotem) i kliknij
   **Continue**, a potem **Authorize**.
7. Jeśli wszystko poszło dobrze, zobaczysz krótki komunikat/animację
   potwierdzającą i bot pojawi się na liście członków Twojego serwera
   (zwykle w osobnej sekcji "Boty" po prawej stronie, offline dopóki
   nie uruchomisz skryptu).

### 2.4 Znajdź ID kanału, na który wysyła PatchBot

1. W aplikacji Discord (desktop albo web) wejdź w **Ustawienia użytkownika**
   (ikonka zębatki przy Twoim nicku na dole po lewej).
2. Po lewej stronie ustawień znajdź sekcję **Zaawansowane** (Advanced)
   i włącz przełącznik **Tryb dewelopera** (Developer Mode).
3. Zamknij ustawienia (Escape), wróć do serwera i znajdź na liście kanałów
   ten, na który PatchBot wysyła powiadomienia.
4. Kliknij na niego prawym przyciskiem myszy (na telefonie: przytrzymaj) —
   na samym dole menu kontekstowego pojawi się nowa opcja
   **Kopiuj ID kanału** (Copy Channel ID). Kliknij ją.
5. Wklej skopiowaną wartość (sam ciąg cyfr, np. `1234567890123456789`)
   do `.env` jako `DISCORD_CHANNEL_ID`.

Uwaga: bot nie musi nic pisać ani mieć uprawnień do wysyłania wiadomości —
tylko czyta ten jeden kanał. Nie musi też widzieć innych kanałów serwera,
jeśli chcesz mu ograniczyć dostęp tylko do tego jednego — w ustawieniach
kanału (Edytuj kanał -> Uprawnienia) możesz ręcznie dodać rolę bota
z dostępem tylko do tego kanału, jeśli reszta serwera ma być dla niego
niewidoczna.

## 3. Slack — Incoming Webhook (krok po kroku)

### 3.1 Załóż aplikację Slacka

1. Wejdź na **https://api.slack.com/apps** i zaloguj się kontem, które ma
   dostęp do workspace `bartlabsdev`.
2. Kliknij zielony przycisk **Create New App** (prawy górny róg).
3. Pojawi się okienko z wyborem: **From scratch** vs **From an app manifest**.
   Wybierz **From scratch** (prościej dla jednego webhooka).
4. W polu **App Name** wpisz np. `PatchBot Bridge`.
5. W polu **Pick a workspace to develop your app in** z listy rozwijanej
   wybierz **bartlabsdev**.
6. Kliknij **Create App**. Zostaniesz przeniesiony na stronę
   **Basic Information** tej aplikacji — to jest jej strona główna,
   z lewym menu nawigacyjnym (podobnie jak w Discordzie).

### 3.2 Włącz Incoming Webhooks

1. W lewym menu znajdź i kliknij **Incoming Webhooks** (może być w sekcji
   nazwanej **Features**, w zależności od układu menu).
2. Zobaczysz przełącznik **Activate Incoming Webhooks** — kliknij go,
   żeby ustawić na **On**. Strona się odświeży i pokaże dodatkowe opcje.
3. Przewiń niżej do sekcji **Webhook URLs for Your Workspace** — na razie
   będzie pusta, kliknij przycisk **Add New Webhook to Workspace**
   (czasem podpisany po prostu jako duży przycisk na dole tej sekcji).
4. Slack przeniesie Cię na ekran autoryzacji (podobny do logowania OAuth) —
   z rozwijanej listy **Post to** wybierz kanał, na który mają trafiać
   powiadomienia od PatchBota (możesz wcześniej utworzyć dedykowany kanał,
   np. `#patchbot-notifications`, żeby nie mieszać z innymi wiadomościami).
5. Kliknij zielony przycisk **Allow** (lub **Authorize**).
6. Wrócisz na stronę **Incoming Webhooks** Twojej aplikacji — w sekcji
   **Webhook URLs for Your Workspace** zobaczysz teraz nowy wiersz z:
   - nazwą kanału, do którego webhook jest przypisany,
   - długim URL-em w formacie
     `https://hooks.slack.com/services/T000000/B000000/xxxxxxxxxxxxxxxxxxxxxxxx`
7. Kliknij przycisk **Copy** obok tego URL-a.
8. Wklej go do `.env` jako `SLACK_WEBHOOK_URL`.

### 3.3 Szybki test (opcjonalnie, zanim uruchomisz cały mostek)

Możesz od razu sprawdzić, czy webhook działa, jednym poleceniem z dowolnego
terminala (np. z Twojego komputera, nie musi to być VPS):

```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test z terminala - jesli to widzisz, webhook dziala"}' \
  "TU_WKLEJ_SWOJ_WEBHOOK_URL"
```

Jeśli w skonfigurowanym kanale na Slacku pojawi się ta wiadomość — webhook
jest gotowy i możesz przejść do uruchomienia mostka.

Uwaga: URL webhooka jest **sekretem** — każdy, kto go zna, może wysyłać
wiadomości na Twój kanał bez żadnego dodatkowego uwierzytelnienia. Traktuj
go jak hasło.

## 4. Instalacja aplikacji w kontenerze

```bash
mkdir -p /opt/patchbot-bridge
# skopiuj tam bridge.py, requirements.txt, .env.example, patchbot-bridge.service
cd /opt/patchbot-bridge

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env   # uzupełnij DISCORD_TOKEN, DISCORD_CHANNEL_ID, SLACK_WEBHOOK_URL
```

Utwórz dedykowanego, niepriuvilegowanego użytkownika systemowego:

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin patchbridge
mkdir -p /var/log/patchbot-bridge
chown -R patchbridge:patchbridge /opt/patchbot-bridge /var/log/patchbot-bridge
```

## 5. Uruchomienie jako usługa systemd

```bash
cp patchbot-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now patchbot-bridge
systemctl status patchbot-bridge
journalctl -u patchbot-bridge -f
```

Po starcie w logu powinieneś zobaczyć coś w stylu:

```
Zalogowano jako PatchBot Bridge#1234 (ID: ...)
Nasłuchuję na kanale #patchbot-notifications (123456789012345678)
```

Test: poczekaj na kolejne powiadomienie od PatchBota — albo (jeśli chcesz
przetestować od razu) napisz dowolną wiadomość na tym kanale — powinna
pojawić się na Slacku.

## 6. Aktualizacje / zarządzanie

```bash
systemctl restart patchbot-bridge   # po zmianie .env lub kodu
systemctl stop patchbot-bridge
journalctl -u patchbot-bridge -n 100 --no-pager   # ostatnie logi
```

## Jak to działa (skrót)

- Bot łączy się do Discorda przez WebSocket (gateway) i cały czas nasłuchuje
  zdarzenia `on_message`.
- Filtruje wiadomości tylko z jednego, skonfigurowanego kanału.
- Jeśli wiadomość ma embed (tak wysyła PatchBot: tytuł gry, opis zmian,
  link, kolor), mostek konwertuje go na Slackowy `attachment` (kolorowy pasek,
  tytuł z linkiem, treść, pola, stopka).
- Wysyła payload POST-em na Slack Incoming Webhook, z 3 próbami i backoffem
  w razie chwilowego błędu sieci.

## Ograniczenia / co warto wiedzieć

- Jeśli VPS/kontener zrestartuje się lub straci połączenie na dłużej,
  wiadomości wysłane przez PatchBota w tym czasie **nie zostaną odtworzone
  wstecznie** — to prosty mostek "live", a nie synchronizacja historii.
  Jeśli chciałbyś dogrywanie zaległych wiadomości po restarcie, da się to
  dodać (zapamiętywanie ostatniego przetworzonego ID wiadomości i doczytanie
  historii kanału przy starcie) — daj znać, jeśli to ważne.
- `discord.py` wymaga Pythona 3.9+; Debian 12 ma domyślnie Python 3.11, więc
  jest ok.
