# Daytect API

Daytect App 後端服務（FastAPI + SQLAlchemy + PostgreSQL），對應 Notion API 文件 v1.1。

## 快速開始

```bash
# 1. 設定環境變數（.env 內容參考 commands.md，需包含 DB、JWT secret、Mail、AI provider 等）

# 2. 啟動服務（Docker）
docker compose up --build

# 3. 套用資料庫遷移（容器內）
docker compose exec app bash
alembic upgrade head
```

服務啟動後預設在 `http://localhost:8000`，API 前綴統一為 `/v1`，互動式文件在 `http://localhost:8000/docs`。

## 身份驗證

除了 `signup` / `signin` / `verification-code` / `refresh-token` 外，其餘 endpoint 都需要帶入登入取得的 access token：

```
Authorization: Bearer <access_token>
```

`{device_id}` / `{analysis_id}` 等資源都會檢查是否屬於目前登入的使用者，不屬於則回 `404`。

---

## Endpoint 一覽

### Auth（無需 token，除了 signout）

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/signup` | 註冊帳號，body 需帶 `email`/`password`/`code`（先呼叫 verification-code 取得） |
| POST | `/v1/verification-code` | 寄送 Email 驗證碼，body 帶 `email`/`type`（`signup` 或 `reset`） |
| POST | `/v1/signin` | 登入，body 帶 `email`/`password`，回傳 `access_token`/`refresh_token` |
| POST | `/v1/refresh-token` | 用 refresh token 換新 token，body 帶 `refresh_token` |
| POST | `/v1/signout` | 登出（需 token），撤銷當前 access token |

### User

| Method | Path | 說明 |
|---|---|---|
| GET | `/v1/users/me` | 取得個人資料 |
| PUT | `/v1/users/me` | 更新個人資料（name/region/sex/height/weight/age... 皆為選填） |
| GET | `/v1/users/me/body-insight` | 取得 BMI 與健康建議 |

### Device

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/devices` | 註冊裝置，body 帶 `mac_address`/`name`/`device_type`/`group` |
| GET | `/v1/devices` | 取得目前使用者所有裝置（依 `my_devices`/`family_devices` 分組） |
| GET | `/v1/devices/{device_id}` | 取得單一裝置詳細資訊 |
| PUT | `/v1/devices/{device_id}` | 更新裝置（name/group/is_share） |
| DELETE | `/v1/devices/{device_id}` | 刪除裝置 |

### Health Data

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/health/{device_id}` | 上傳健康數據，body 帶 `recorded_at` + 各項指標（sleep/heart_rate/blood_pressure...），同一天重複上傳會合併（心率為累加，其餘欄位覆蓋） |
| GET | `/v1/health/{device_id}/dates` | 取得該裝置有上傳資料的日期清單 |
| GET | `/v1/health/{device_id}?date=YYYY-MM-DD` | 取得指定日期的健康數據與各指標狀態（不帶 `date` 預設今天） |

### Dashboard

| Method | Path | 說明 |
|---|---|---|
| GET | `/v1/dashboard/{device_id}?date=YYYY-MM-DD` | 取得首頁總覽：裝置狀態、今日健康分數/趨勢/AI 洞察、藍牙超出範圍提醒。**首次呼叫若當天 AI 分析尚未生成，會自動觸發背景生成**，回傳 `analysis_status.status = processing`，需稍後重新呼叫直到變成 `ready` |

### AI Health Analysis

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/analysis/{device_id}` | 手動觸發/強制重新生成 AI 分析，body 帶 `date`/`range`（daily/weekly/monthly），立即回傳 `status=processing` |
| GET | `/v1/analysis/{analysis_id}/status` | 查詢某次分析的生成狀態 |
| GET | `/v1/analysis/{device_id}/dates?range=daily` | 取得已生成分析的日期清單 |
| GET | `/v1/analysis/{device_id}?date=YYYY-MM-DD&range=daily` | 取得每日 AI 分析內容（僅支援 `range=daily`；若尚未生成會自動觸發，同 Dashboard 邏輯） |

### Health Detail Reports（Weekly / Monthly）

| Method | Path | 說明 |
|---|---|---|
| GET | `/v1/reports/{device_id}?range=weekly&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | 取得週報或月報（`range` 僅支援 `weekly`/`monthly`），同樣是首次呼叫自動觸發背景生成，需輪詢直到 `ready` |

### Feedback

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/feedback` | 送出意見回饋，body 帶 `type`/`subject`/`message` |

### About

| Method | Path | 說明 |
|---|---|---|
| GET | `/v1/about` | 取得 App 基本資訊（版本、官網、隱私權政策連結等，固定值） |

---

## 範例：完整流程（curl）

```bash
BASE=http://localhost:8000/v1

# 1. 寄驗證碼
curl -X POST $BASE/verification-code -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","type":"signup"}'

# 2. 註冊
curl -X POST $BASE/signup -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"12345678*","code":"1234"}'

# 3. 登入，取得 access_token
TOKEN=$(curl -s -X POST $BASE/signin -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"12345678*"}' | jq -r .access_token)

# 4. 註冊裝置
DEVICE_ID=$(curl -s -X POST $BASE/devices -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mac_address":"AA:BB:CC:DD:EE:FF","name":"My Band","device_type":"wearable","group":"my_devices"}' \
  | jq -r .id)

# 5. 上傳今天的健康數據
curl -X POST $BASE/health/$DEVICE_ID -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "recorded_at": "2026-06-21T08:30:00Z",
    "sleep": {"light":240,"deep":120,"wake":30,"total":390,"unit":"minutes"},
    "heart_rate": [{"time":"2026-06-21T08:00:00Z","value":82,"unit":"bpm"}],
    "blood_pressure": {"systolic":120,"diastolic":80,"unit":"mmHg"},
    "blood_oxygen": {"value":96,"unit":"%"},
    "body_temperature": {"value":37.1,"unit":"celsius"},
    "activity": {"steps":7200,"calories":320,"distance":5.4,"distance_unit":"km"}
  }'

# 6. 取得 Dashboard（第一次可能回 processing，幾秒後重打會變 ready）
curl $BASE/dashboard/$DEVICE_ID -H "Authorization: Bearer $TOKEN"
```

## 專案結構

```
src/
  auth/          # 註冊、登入、token
  user/          # 個人資料、BMI
  user_device/   # 裝置管理
  healthcare/    # 健康數據、Dashboard、AI 分析、週月報告
  feedback/      # 意見回饋
  about/         # App 資訊
  core/          # DB、JWT、Email、AI client、共用設定
```

每個業務模組依 `models/ schemas/ services/ api.py` 分層：`models` 為 SQLAlchemy ORM、`schemas` 為 Pydantic request/response、`services` 為商業邏輯、`api.py` 為路由層。
