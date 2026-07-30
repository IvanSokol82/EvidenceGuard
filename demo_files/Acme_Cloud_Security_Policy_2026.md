# Acme Cloud Security & Compliance Policy (Version 2026.1)

## 1. Data Encryption Standards
- **Encryption at Rest**: All customer databases, file storage, and snapshot backups are encrypted using AES-256 bit encryption with customer-managed keys via AWS KMS.
- **Encryption in Transit**: All network traffic across public boundaries uses TLS 1.3 with mandatory Perfect Forward Secrecy (PFS).

## 2. Infrastructure & Data Residency
- **Primary Hosting**: AWS Frankfurt Region (eu-central-1), Germany.
- **Failover Region**: AWS Ireland Region (eu-west-1), Ireland.
- **Data Residency Guarantee**: All primary data and backups strictly reside within the European Union (EU).

## 3. Access Control & Authentication
- **Single Sign-On (SSO)**: Natively supports SAML 2.0 and OpenID Connect (OIDC) protocols (Okta, Azure AD, PingIdentity).
- **Multi-Factor Authentication (MFA)**: Mandatory for all personnel accessing production environments.

## 4. Disaster Recovery & Incidents
- **Recovery Point Objective (RPO)**: <= 15 minutes.
- **Recovery Time Objective (RTO)**: <= 1 hour.
- **Incident Notification SLA**: Affected clients are notified within 24 hours of a confirmed breach.

## 5. Artificial Intelligence & Data Usage
- **AI Model Training Policy**: Acme Cloud NEVER permits third-party AI subprocessors to train models on customer data.
