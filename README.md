# exKhataBot - Evolution API (WhatsApp) with Supabase

This project sets up [Evolution API v2](https://github.com/EvolutionAPI/evolution-api) to connect WhatsApp with [Supabase](https://supabase.com) (PostgreSQL Database & Storage).

---

## 📌 Requirements from Supabase

To connect Evolution API with your Supabase project, you only need your **Database Connection URI**.

### How to Get Your Database Connection URI:
1. Open your [Supabase Dashboard](https://supabase.com/dashboard).
2. Select your project.
3. Click on the **Project Settings** (gear icon) in the left sidebar.
4. Navigate to **Database**.
5. Scroll down to **Connection string** and select **URI**.
6. Copy the URI string:
   - **Direct connection (Port 5432):**
     ```text
     postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
     ```
   - **Connection pooler (Session mode - Port 6543, recommended for IPv4):**
     ```text
     postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
     ```
7. Append `?schema=evolution_api` to the end of the URI:
   ```text
   postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres?schema=evolution_api
   ```
   > **Note:** Appending `?schema=evolution_api` creates all Evolution API tables in a separate schema, keeping your `public` schema clean for your application data.

---

## 🚀 Setup Steps

### 1. Configure `.env`
Open the `.env` file in the project root and update `DATABASE_CONNECTION_URI`:
```env
DATABASE_CONNECTION_URI=postgresql://postgres:YourActualPassword@db.your-ref.supabase.co:5432/postgres?schema=evolution_api
```

*(Optional)* If your password contains special characters like `@`, `#`, `!`, or `$`, make sure to URL-encode them (e.g. `@` -> `%40`).

---

### 2. Start Docker Containers
Ensure **Docker Desktop** is running, then run:

```bash
docker compose up -d
```

Check the container logs to verify that Evolution API connects to Supabase and initializes:

```bash
docker compose logs -f evolution-api
```

---

### 3. Access Evolution API & Swagger Docs
Once started, Evolution API is available at:
- **API Base URL:** `http://localhost:8080`
- **Swagger Documentation:** `http://localhost:8080/docs`

Your Global API Key is configured in `.env`:
- Header: `apikey: <YOUR_AUTHENTICATION_API_KEY>`

---

### 4. Create an Instance & Connect WhatsApp

You can create an instance by making a POST request via curl, Postman, or the Swagger UI:

#### cURL:
```bash
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: <YOUR_AUTHENTICATION_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "exkhatabot",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS"
  }'
```

#### Get QR Code to Scan:
```bash
curl -X GET http://localhost:8080/instance/connect/exkhatabot \
  -H "apikey: <YOUR_AUTHENTICATION_API_KEY>"
```

Open WhatsApp on your mobile phone:
**Settings > Linked Devices > Link a Device** and scan the QR code.

---

## 🗄️ Architecture & Components

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────────┐
│    WhatsApp     │ <---> │  Evolution API  │ <---> │  Supabase Postgres  │
│  (Mobile Phone) │       │ (Docker: :8080) │       │ (Schema: evolution) │
└─────────────────┘       └────────┬────────┘       └─────────────────────┘
                                   │
                           ┌───────┴───────┐
                           │  Redis Cache  │
                           │  (Docker)     │
                           └───────────────┘
```
