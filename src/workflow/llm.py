import json
import re
from typing import Protocol


class LLMProvider(Protocol):
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        ...


class MockLLMProvider:
    """
    Deterministic Mock LLM Provider for local development and network-free unit tests.
    Parses prompts and returns structured JSON/text tailored to questionnaire classification,
    normalization, answer drafting, and evidence validation.
    """

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        prompt_lower = prompt.lower()

        if "extract" in prompt_lower or "вилучити" in prompt_lower:
            # Extract actual lines from prompt text (numbered or with '?')
            parts = prompt.split("\n\n")
            raw_text = parts[-1] if len(parts) > 1 else prompt
            lines = [
                line.strip()
                for line in raw_text.split("\n")
                if line.strip() and (re.match(r"^\d+[\.\)]", line.strip()) or "?" in line)
            ]

            if lines:
                return json.dumps([{"number": i + 1, "text": q} for i, q in enumerate(lines)])
            return json.dumps([
                {"number": 1, "text": "Do you encrypt customer data at rest and in transit?"},
                {"number": 2, "text": "Do you hold a valid SOC 2 Type II or ISO 27001 certification?"},
                {"number": 3, "text": "Where is customer data physically stored and hosted?"},
            ])

        elif "classify" in prompt_lower or "класифікувати" in prompt_lower:
            if "encrypt" in prompt_lower:
                return json.dumps({
                    "topic": "Encryption",
                    "tags": ["AES-256", "data-at-rest", "TLS"],
                    "is_multi_part": True,
                    "sub_questions": ["Is data encrypted at rest?", "Is data encrypted in transit?"],
                    "risk_level": "high",
                })
            elif "soc 2" in prompt_lower or "iso" in prompt_lower or "certification" in prompt_lower or "pci" in prompt_lower:
                return json.dumps({
                    "topic": "Compliance",
                    "tags": ["SOC2", "ISO27001"],
                    "is_multi_part": False,
                    "sub_questions": [],
                    "risk_level": "critical",
                })
            else:
                return json.dumps({
                    "topic": "Infrastructure",
                    "tags": ["hosting", "data-residency"],
                    "is_multi_part": False,
                    "sub_questions": [],
                    "risk_level": "medium",
                })

        elif "draft answer" in prompt_lower or "чернетка" in prompt_lower:
            if "context evidence:\n[]" in prompt_lower or "no evidence" in prompt_lower or "not found" in prompt_lower:
                return json.dumps({
                    "draft_text": "Статус: NEEDS_HUMAN_INPUT\n\nПричина: Жодного затвердженого доказу не знайдено для підтвердження цієї відповіді.\n\nРекомендована дія: Підтвердити політику або додати новий затверджений документ-джерело.",
                    "facts": [],
                    "assumptions": [],
                    "missing_information": ["Не знайдено затвердженого доказу в базі знань."],
                    "validation_status": "NO_EVIDENCE",
                    "model_name": "EvidenceGuard-GuardEngine",
                    "version": 1,
                })

            if "encrypt" in prompt_lower:
                text = (
                    "Так, усі дані клієнтів повністю шифруються як у стані спокою, так і під час передачі.\n\n"
                    "• У стані спокою (At Rest): Дані шифруються за алгоритмом AES-256 з керуванням ключами через AWS KMS.\n"
                    "• Під час передачі (In Transit): Використовується суворий протокол TLS 1.3 із Perfect Forward Secrecy (PFS)."
                )
                facts = [
                    "Шифрування у стані спокою: AES-256 bit via AWS KMS",
                    "Шифрування у передачі: TLS 1.3 з Perfect Forward Secrecy",
                ]
            elif "sso" in prompt_lower or "saml" in prompt_lower or "mfa" in prompt_lower:
                text = (
                    "Так, платформа підтримує корпоративний Single Sign-On (SSO) та багатофакторну автентифікацію.\n\n"
                    "• Підтримувані протоколи: SAML 2.0 та OpenID Connect (OIDC) для Okta, Azure AD, PingIdentity.\n"
                    "• Багатофакторна автентифікація (MFA): Обов'язкова для всього персоналу з доступом до продакшну."
                )
                facts = [
                    "SSO протоколи: SAML 2.0, OIDC (Okta, Azure AD)",
                    "MFA є обов'язковою для доступу до продакшну",
                ]
            elif "ai" in prompt_lower or "llm" in prompt_lower or "model" in prompt_lower:
                text = (
                    "Ні, дані клієнтів категорично НЕ передаються стороннім ШІ-постачальникам для навчання моделей.\n\n"
                    "• Політика використання ШІ: Acme Cloud забороняє передачу будь-яких наборів даних стороннім субпідрядникам.\n"
                    "• Навчання моделей: Жодні сторонні LLM-моделі не тренуються на даних клієнтів без попередньої письмової згоди."
                )
                facts = [
                    "Заборона передачі даних стороннім ШІ-субпідрядникам",
                    "Відсутність навчання сторонніх LLM-моделей на даних клієнтів",
                ]
            elif "host" in prompt_lower or "data center" in prompt_lower or "germany" in prompt_lower or "frankfurt" in prompt_lower:
                text = (
                    "Основні продакшн бази даних фізично розміщені у дата-центрах AWS Frankfurt (eu-central-1), Німеччина.\n\n"
                    "• Data Residency: Усі первинні дані та резервні копії зберігаються виключно в межах Європейського Союзу (EU).\n"
                    "• Failover Регіон: Резервний регіон аварійного відновлення — AWS Ireland (eu-west-1)."
                )
                facts = [
                    "Первинний хостинг: AWS Frankfurt (eu-central-1), Німеччина",
                    "Гарантія зберігання даних виключно в межах ЄС",
                ]
            else:
                text = "Інформацію підтверджено у затвердженій Політиці безпеки компанії на основі доданих документів бази знань."
                facts = ["Інформацію верифіковано у базі знань."]

            return json.dumps({
                "draft_text": text,
                "facts": facts,
                "assumptions": [],
                "missing_information": [],
                "validation_status": "SUPPORTED",
                "model_name": "EvidenceGuard-Copilot",
                "version": 1,
            })

        elif "validate" in prompt_lower or "валідація" in prompt_lower:
            if "high risk" in prompt_lower or "critical" in prompt_lower:
                return json.dumps({
                    "validation_status": "HIGH_RISK_CLAIM",
                    "passed": False,
                    "reason": "Заява потребує підтвердження офіційним сертифікатом.",
                    "citations": [],
                })
            return json.dumps({
                "validation_status": "SUPPORTED",
                "passed": True,
                "reason": "Відповідь повністю підтверджена доказами.",
                "citations": ["Sec 1"],
            })

        return json.dumps({"status": "ok", "message": "Generic LLM response"})


def get_llm_provider() -> LLMProvider:
    return MockLLMProvider()
