# MVP Scope Definition: EvidenceGuard

---

## 1. Включено в MVP (In Scope for MVP)

### A. База знань компанії (Company Knowledge Base)
- **Завантаження документів:** PDF, DOCX, Markdown (.md), Текст (.txt), CSV, XLSX.
- **Метадані документів:**
  - Title, Document Type (Policy, Architecture, Audit, FAQ, etc.)
  - Owner Team (Security, Legal, Engineering, Ops)
  - Approval Status (`draft`, `approved`, `deprecated`, `expired`)
  - Version (напр. `v1.2`)
  - Validity Range (`valid_from`, `valid_to`)
  - Upload Timestamp, Source URI, Sensitivity Level (`internal`, `confidential`, `restricted`)

### B. Інгестія опитувальників (Questionnaire Ingestion)
- Ввід через вставку тексту (pasted text).
- Завантаження файлів: PDF, DOCX, XLSX, `.eml` (email).
- Проста веб-форма для введення поодиноких запитань.

### C. Вилучення та нормалізація запитань (Question Extraction & Normalization)
- Розбиття документа на окремі атомарні запитання.
- Збереження оригінального формулювання (original wording).
- Класифікація за топіками (напр. Encryption, Access Control, Business Continuity, Compliance, Subprocessors).
- Детекція складних/багатокомпонентних запитань (multi-part questions).
- Оцінка рівня ризику (Low, Medium, High, Critical).

### D. Гібридний RAG (Hybrid Retrieval)
- Семантичний пошук через `pgvector` (Cosine distance).
- Повнотекстовий пошук через PostgreSQL `tsvector` (BM25-like search with ranking).
- Метадані-фільтрація (`approval_status == approved`, `valid_to >= current_date`).
- Ранжування через **Reciprocal Rank Fusion (RRF)**.
- Множники довіри джерел (Trust Multipliers): політики та архітектура вище за маркетингові матеріали чи старі опитувальники.

### E. Генерація та Валідація відповідей (Drafting & Hallucination Guard)
- Генерація відповідей **виключно** з наданого контексту.
- Обов'язкове посилання на точне джерело (цитата, документ, версія, сторінка/секція).
- Відокремлення фактів, припущень та відсутніх даних.
- Заборона малювання відсутніх сертифікатів, SLA, RPO/RTO, регіонів зберігання та юридичних гарантій.

### F. Інтерфейс перевірки людиною (Human Review Queue)
- Черга перевірки відповідей з можливістю дій: `Approve`, `Edit`, `Reject`, `Request Evidence`, `Escalate`.
- Перегляд знайдених доказів (Evidence Viewer).
- Чітке кольорове маркування статусів.

### G. Експорт та звітність (Response Output)
- Табличний перегляд відповідей.
- Генерація чернетки Email (Email Draft).
- Експорт у форматі Markdown та JSON.

### H. Журнал аудиту (Audit Trail)
- Повна відтворюваність кожної відповіді: початкове запитання, використані фрагменти (chunks), версія документа, параметри пошуку, модель, рішення та ID рев'юера.

---

## 2. Не включено в MVP (Non-Goals / Excluded from MVP)
- **Автоматична відправка email:** Жодний лист не надсилається авто-ботом.
- **Юридичні консультації та гарантії комплаєнсу:** Система готує лише чернетки.
- **Автономне затвердження документів:** Людина завжди приймає фінальне рішення.
- **Прямі інтеграції з CRM / Drive / Notion / Slack / Jira:** Усі файли завантажуються через UI/API.
- **Багатотенентний білінг (Multi-tenant billing) та складний RBAC enterprise-рівня.**
- **Скрейпінг веб-сайтів або LinkedIn.**
- **Автоматичне виконання дій з виправлення (Remediation actions).**
