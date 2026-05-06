# 🎫 Ticket Support System — Full Stack

A real-time customer support ticketing platform split into two fully independent systems sharing a single MongoDB database and WebSocket real-time layer.

---

## 🆕 Enhanced Features (v2)

### 1. 💬 Typing Indicators (Bidirectional)
- When a **support engineer** types, the customer sees **"Agent is typing..."** with animated dots
- When a **customer** types, the support engineer sees **"Customer is typing..."** with animated dots
- Typing stops automatically after 2 seconds of inactivity or on message send
- Works on **both sides** in real time via WebSocket

### 2. ⚡ Fully Real-Time — No Refresh Needed
- **Customer side:** Ticket creation, chat messages, status changes all reflect instantly
- **Support side:** New tickets appear in the open pool immediately without refresh
- When a new ticket is created, it **auto-adds** to the open pool list in real time
- Status changes (taken → in_progress, resolved, closed) update all connected clients instantly
- WebSocket connections **auto-reconnect** after disconnect (3s retry)

### 3. 🗨️ Chat Widget Auto-Opens on Login
- After a customer logs in, the floating chat widget **automatically opens** showing their tickets
- No manual click required — the widget appears in the corner immediately after authentication

### 4. 🔔 Real-Time Notifications for Support Engineers
- When a new ticket is created, a **red badge** appears on the notification bell automatically
- The notification panel **auto-opens** to show the incoming ticket — no refresh needed
- Notifications include ticket number, subject, and priority
- Engineers can click a notification to jump directly to that ticket

### 5. 🔒 Closed Ticket Enforcement
- When a support engineer **closes** a ticket, the customer's chat input is **immediately disabled** via WebSocket `status_update` event
- A banner appears: *"This ticket is closed. Need more help?"* with a **Raise New Ticket** button
- The backend also **blocks** any message sent to a closed ticket at the server level (double protection)
- Customer must open a fresh ticket for any new issues

### 6. 👥 Team-Based Ticket Visibility
- Each support engineer belongs to a **team** (team1, team2, team3)
- Engineers **only see tickets assigned to their team** in "My Tickets" / "All Tickets"
- **Open pool** (unassigned tickets) is visible to all engineers — anyone can pick them up
- When an engineer takes a ticket, the ticket is **tagged with their team**
- **Admin** can see **all tickets across all teams** with no restriction
- Team is assigned by admin when creating an engineer account
- Team badge is shown in the support engineer's dashboard header

---

## 📐 Project Architecture

```
ticket_system/
├── customer-system/             ← Customer-facing app (Port 3000 + 8000)
│   ├── frontend/                ← React floating chat widget (Port 3000)
│   └── backend/                 ← FastAPI API — customer routes only (Port 8000)
│
├── admin-support-system/        ← Staff dashboard app (Port 5174 + 8001)
│   ├── frontend/                ← React full dashboard (Port 5174)
│   └── backend/                 ← FastAPI API — all routes + notifications (Port 8001)
│
├── insert_data.py               ← Seed script for MongoDB (roles, engineers, customers)
└── README.md
```

Both systems connect to the **same MongoDB database** and share the same JWT secret, enabling seamless cross-system authentication and real-time communication.

---

## 📁 Folder Structure (Detailed)

```
customer-system/
├── backend/
│   ├── app/
│   │   ├── config/            db.py, settings.py
│   │   ├── constants/         ticket_status.py, roles.py, websocket_events.py
│   │   ├── database/          collection placeholders
│   │   ├── dependencies/      auth_dependency.py, role_dependency.py
│   │   ├── routes/            auth_routes.py, ticket_routes.py, message_routes.py
│   │   ├── schemas/           pydantic models
│   │   ├── services/          auth_service.py, ticket_service.py, message_service.py
│   │   ├── utils/             jwt.py, hash.py, shared.py
│   │   ├── websocket/         manager.py (with typing), websocket_routes.py
│   │   └── main.py            FastAPI app — customer CORS only
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                   (create from .env.example)
│
└── frontend/
    ├── src/
    │   ├── components/
    │   │   └── ChatWidget.jsx  ★ NEW — floating chat widget
    │   ├── context/            AuthContext.jsx, ThemeContext.jsx
    │   ├── services/           api.js — customer-only endpoints
    │   └── App.jsx             Renders <ChatWidget /> only
    ├── vite.config.js          Port 3000, proxies to :8000
    └── package.json

admin-support-system/
├── backend/
│   ├── app/
│   │   ├── ...                (same structure as customer)
│   │   ├── websocket/
│   │   │   ├── manager.py     (with typing indicator broadcast)
│   │   │   ├── notification_manager.py
│   │   │   └── websocket_routes.py  (chat + notification WS)
│   │   └── main.py            FastAPI app — admin CORS + notification broadcaster
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/
    ├── src/
    │   ├── components/
    │   │   └── ChatPanel.jsx   ★ UPDATED — typing indicators + identity rules
    │   ├── context/            AuthContext.jsx (staff), ThemeContext.jsx
    │   ├── pages/
    │   │   ├── LoginPage.jsx   Staff-only login
    │   │   ├── admin/          AdminDashboard.jsx
    │   │   └── support/        SupportDashboard.jsx ★ UPDATED — auto-open on accept
    │   ├── services/           api.js — staff endpoints + WS helpers
    │   └── App.jsx             Login → support | admin routing
    ├── vite.config.js          Port 5174, proxies to :8001
    └── package.json
```

---

## 🚀 How to Run

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB running on `localhost:27017`

### 1. Seed the Database (run once)
```bash
pip install -r customer-system/backend/requirements.txt
python insert_data.py
```

This creates roles, sample support engineers, and sample customers.

---

### 2. Customer Backend (Port 8000)
```bash
cd customer-system/backend
cp .env.example .env          # edit if needed
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

---

### 3. Customer Frontend (Port 3000)
```bash
cd customer-system/frontend
npm install
npm run dev
```
Open: http://localhost:3000

The customer sees **only the floating chat widget** in the bottom-right corner.

---

### 4. Admin/Support Backend (Port 8001)
```bash
cd admin-support-system/backend
cp .env.example .env          # same .env values as customer backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```
API docs: http://localhost:8001/docs

---

### 5. Admin/Support Frontend (Port 5174)
```bash
cd admin-support-system/frontend
npm install
npm run dev
```
Open: http://localhost:5174

Staff log in with their email/password. Admin and support engineers both use this URL.

---

## 🔌 Ports Reference

| Service                   | Port  | URL                        |
|---------------------------|-------|----------------------------|
| Customer Frontend         | 3000  | http://localhost:3000      |
| Customer Backend API      | 8000  | http://localhost:8000      |
| Admin/Support Frontend    | 5174  | http://localhost:5174      |
| Admin/Support Backend API | 8001  | http://localhost:8001      |
| MongoDB                   | 27017 | mongodb://localhost:27017  |

---

## ⚙️ Environment Variables

Both backends use the same variables (same DB, same JWT secret):

| Variable                    | Default                          | Description                     |
|-----------------------------|----------------------------------|---------------------------------|
| `SECRET_KEY`                | `your-super-secret-key-...`      | JWT signing secret              |
| `ALGORITHM`                 | `HS256`                          | JWT algorithm                   |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15`                           | Access token TTL                |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7`                              | Refresh token TTL               |
| `MONGODB_URL`               | `mongodb://localhost:27017`      | MongoDB connection string       |
| `DATABASE_NAME`             | `ticket_support_db`              | Database name                   |

Frontend environment (optional, defaults built into vite.config.js):

| Variable               | Default                   | Description                  |
|------------------------|---------------------------|------------------------------|
| `CUSTOMER_BACKEND_URL` | `http://localhost:8000`   | Customer backend URL         |
| `ADMIN_BACKEND_URL`    | `http://localhost:8001`   | Admin/support backend URL    |

---

## 🔄 WebSocket Flow

### Chat WebSocket: `ws://host/ws/{ticket_id}?token=<JWT>`

Both backends expose this endpoint. Used by customers (port 8000) and support engineers (port 8001).

**Client → Server messages:**
```json
{ "type": "message", "message": "Hello!", "message_type": "text" }
{ "type": "typing", "is_typing": true }
```

**Server → Client messages:**
```json
{ "type": "history",      "messages": [...] }
{ "type": "message",      "message": { sender_type, sender_name, message, timestamp } }
{ "type": "typing",       "sender_type": "customer"|"support", "is_typing": true|false }
{ "type": "status_update","ticket_id": 1, "ticket_number": "TCK-1", "status": "resolved" }
```

### Notification WebSocket (admin backend only): `ws://host/ws/notifications/live?token=<JWT>`

Support engineers connect here to receive real-time ticket events.

**Server → Client events:**
```json
{ "event": "ticket_created",  "ticket_id": 1, "ticket_number": "TCK-1", "subject": "...", "priority": "high" }
{ "event": "ticket_taken",    "ticket_id": 1, "engineer_id": 101 }
{ "event": "ticket_resolved", "ticket_id": 1, "ticket_number": "TCK-1" }
{ "event": "ticket_closed",   "ticket_id": 1, "ticket_number": "TCK-1" }
{ "event": "ticket_reopened", "ticket_id": 1, "engineer_id": 101 }
```

**Client → Server (engineer actions):**
```json
{ "action": "attend", "ticket_id": 1 }
```

---

## ✨ Key Features

### 1. Separated Systems
- Customer app on port 3000/8000 — no dashboard, no navigation
- Admin/Support app on port 5174/8001 — full dashboard with RBAC

### 2. Floating Chat Widget (Customer)
- Bottom-right corner button toggles widget open/closed
- Inline login/register — no redirect to separate page
- Ticket list → create ticket → chat, all within the widget
- Fully embeddable: drop `<ChatWidget />` into any page

### 3. Auto System Message
- When a customer creates a ticket, a professional welcome message is **automatically inserted**:
  > "Thank you for contacting support. Your ticket has been received and will be reviewed shortly. Please wait while we connect you with an agent."
- Displayed with a bot icon, visually distinct from chat messages

### 4. Auto-Open Chat on Accept
- When a support engineer clicks **Accept** on a ticket, the chat for that ticket opens immediately
- Also triggered when the notification WS receives `ticket_taken` with the engineer's own ID
- Tab switches to "My Tickets" automatically

### 5. Typing Indicators (Bi-directional)
- Customer side: sees **"Agent is typing..."** with animated dots
- Support side: sees **"Customer is typing..."** with animated dots
- Indicators automatically stop after 1.5 seconds of inactivity or on disconnect

### 6. Identity Rules
- **Support engineer name IS visible** to the customer (shown as label on messages)
- **Customer personal name is HIDDEN** from support engineers — messages show "Customer" instead
- System messages show a bot icon with no name

### 7. Shared Real-time Infrastructure
- Both systems use the same MongoDB database
- Tickets, messages, and status changes are instantly reflected on both sides

---

## 🔐 Auth Flow

**Customer:**
1. Register → `POST /auth/customer/register`
2. Login → `POST /auth/customer/login` → returns `access_token` + `refresh_token`
3. Token stored in `sessionStorage` (tab-isolated)

**Staff (support/admin):**
1. Login → `POST /auth/staff/login`
2. Admin creates engineers → `POST /auth/staff/create` (admin only)

---

## 🗄️ Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Frontend   | React 18, Vite, Tailwind CSS, Lucide|
| Backend    | FastAPI, Python 3.11+               |
| Database   | MongoDB (Motor async driver)        |
| Real-time  | WebSockets (native FastAPI)         |
| Auth       | JWT (python-jose), bcrypt           |
| State      | React Context + sessionStorage      |

