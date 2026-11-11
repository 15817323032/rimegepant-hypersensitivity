# -*- coding: utf-8 -*-
"""
瑞美吉泮（rimegepant ODT）口腔/超敏切口 —— MedDRA PT 病例定义与检索策略配置

设计原则
--------
1. 所有 PT 名称一律使用 FAERS REAC 表中的原始大写形式（MedDRA PT），
   通过 normalize() 做清洗后精确匹配，不做模糊匹配（避免假阳性）。
2. 分层定义：CORE_ORAL / PHARYNGEAL_AIRWAY / SYSTEMIC_HYPER / SENSORY / EXCIPIENT
   五个子集可分别统计，也可合并为复合终点 ORAL_HYP_COMPOSITE。
3. 子集划分对应不同的临床严重性层级，是本研究"切口"的核心资产：
   - CORE_ORAL + SENSORY  -> ODT 局部接触性/感觉性事件（机制上最可能来自口崩片剂型本身）
   - PHARYNGEAL_AIRWAY    -> 气道受累，是超敏反应升级为严重事件的转折点
   - SYSTEMIC_HYPER       -> 全身性超敏（含 anaphylaxis），对应 FDA 2025-08 标签修订
   - EXCIPIENT            -> 辅料（明胶/甘露醇/三氯蔗糖/薄荷香精）相关报告
"""

# ---------------------------------------------------------------------------
# 1. 目标药物识别
# ---------------------------------------------------------------------------
# FAERS DRUG.drugname 为自由文本，需覆盖商品名、研发代号、盐型与拼写变体。
# 注意：NURTEC 亦可能出现在其他语境，但作为药品名出现时归属明确。
DRUG_PATTERNS = [
    r"RIMEGEPANT",          # 通用名
    r"RIMEGEPANT\s*SULFATE",
    r"RIMEGEPANT\s*BENZOATE",
    r"NURTEC",              # 美国商品名（Nurtec ODT）
    r"VYDURA",              # 欧盟/英国商品名
    r"BMS[\s\-]?927711",    # 研发代号
    r"BMS927711",
]

# 对照药（用于阳性对照与类效应比较，可选模块）
COMPARATOR_PATTERNS = {
    "Ubrogepant": [r"UBROGEPANT", r"UBRELVY"],
    "Atogepant": [r"ATOGEPANT", r"AQUIPTA", r"QULIPTA"],
    "Erenumab": [r"ERENUMAB", r"AIMOVIG"],
    "Topiramate": [r"TOPIROMATE", r"TOPIRAMATE", r"TOPAMAX"],
}

# ---------------------------------------------------------------------------
# 2. 口腔 / 超敏 PT 病例定义
# ---------------------------------------------------------------------------
# 依据：已发表 FAERS 研究报告的 rimegepant 口腔相关信号
#   - 何华康 2025（中国新药与临床杂志）：肿舌、口部感觉异常、咽部肿胀、嗜睡
#   - 周丽 2024（现代药物与临床）：舌不适、晨吐、醉酒感、鼻水肿、赋形剂反应
#   - Hu 2024（J Headache Pain）：reaction to food additive/excipient、motion sickness
#   - Song 2025（J Headache Pain）：feeling abnormal（敏感性分析后最强）
# 并补充 MedDRA 层次结构上的邻近 PT，形成完整病例定义。

CORE_ORAL = [
    # 舌
    "SWOLLEN TONGUE", "TONGUE OEDEMA", "TONGUE EDEMA", "TONGUE DISORDER",
    "TONGUE ERUPTION", "GLOSSODYNIA", "GLOSSITIS", "TONGUE BLISTERING",
    "TONGUE COATED", "TONGUE DRY", "TONGUE HAEMORRHAGE",
    # 唇
    "LIP SWELLING", "LIP OEDEMA", "LIP EDEMA", "LIP PAIN", "LIP DISORDER",
    "CHEILITIS", "ANGULAR CHEILITIS",
    # 口腔黏膜
    "ORAL DISCOMFORT", "ORAL PAIN", "ORAL MUCOSAL BLISTERING", "ORAL MUCOSITIS",
    "STOMATITIS", "APHTHOUS STOMATITIS", "APHTHOUS ULCER", "MOUTH ULCERATION",
    "ORAL MUCOSAL ERYTHEMA", "MUCOSAL ULCERATION", "ORAL LICHEN PLANUS",
    "MOUTH SWELLING", "ORAL MUCOSAL EXFOLIATION",
    # 唾液腺
    "SALIVARY HYPERSECRETION", "SALIVARY GLAND ENLARGEMENT", "DRY MOUTH",
    "PAROTITIS", "SIALOADENITIS",
]

SENSORY = [
    # 口部感觉异常（何华康 2025 检出的说明书未载明信号）
    "PARAESTHESIA ORAL", "ORAL PARAESTHESIA", "HYPOAESTHESIA ORAL",
    "BURNING SENSATION", "BURNING MOUTH SYNDROME",
    # 味觉（关联薄荷香精/三氯蔗糖辅料）
    "DYSGEUSIA", "AGEUSIA", "TASTE DISORDER", "PRODUCT TASTE PERCEPTION DISORDER",
    "HYPOSMIA", "PAROSMIA",
    # 局部感觉异常
    "THROAT IRRITATION", "PHARYNGEAL PARAESTHESIA", "TONGUE PARAESTHESIA",
]

PHARYNGEAL_AIRWAY = [
    "PHARYNGEAL SWELLING", "PHARYNGEAL OEDEMA", "PHARYNGEAL EDEMA",
    "PHARYNGEAL ERYTHEMA", "PHARYNGEAL INFLAMMATION", "OROPHARYNGEAL PAIN",
    "OROPHARYNGEAL SPASM", "OROPHARYNGEAL BLISTERING", "THROAT TIGHTNESS",
    "LARYNGEAL OEDEMA", "LARYNGEAL EDEMA", "LARYNGOSPASM", "DYSPHAGIA",
    "DYSPHONIA", "STRIDOR", "SENSATION OF FOREIGN BODY", "GLOBUS PHRENICUS",
    "THROAT LESION",
]

SYSTEMIC_HYPER = [
    # 严重超敏（FDA 2025-08 标签新增禁区）
    "ANAPHYLACTIC REACTION", "ANAPHYLACTIC SHOCK", "ANAPHYLAXIS",
    "HYPERSENSITIVITY", "DRUG HYPERSENSITIVITY", "TYPE I HYPERSENSITIVITY",
    "TYPE III IMMUNE COMPLEX MEDIATED REACTION", "TYPE IV HYPERSENSITIVITY",
    "IMMEDIATE POST-INJECTION REACTION", "INFUSION RELATED REACTION",
    "SERUM SICKNESS", "SERUM SICKNESS-LIKE REACTION",
    # 血管性水肿与皮肤
    "ANGIOEDEMA", "ANGIONEUROTIC OEDEMA", "URTICARIA", "URTICARIAL VASCULITIS",
    "RASH", "RASH MACULO-PAPULAR", "RASH PAPULAR", "RASH ERYTHEMATOUS",
    "RASH PRURITIC", "PRURITUS", "PRURITUS GENERALISED", "FLUSHING",
    "DERMATITIS ALLERGIC", "ECZEMA", "ERYTHEMA MULTIFORME",
    # 头面部水肿
    "SWELLING FACE", "FACIAL OEDEMA", "PERIORBITAL OEDEMA", "EYE SWELLING",
    "EYELID OEDEMA", "NASAL OEDEMA", "CONJUNCTIVAL OEDEMA",
    # 气道/全身
    "DYSPNOEA", "BRONCHOSPASM", "WHEEZING", "HYPOXIA",
    "BLOOD PRESSURE DECREASED", "CIRCULATORY COLLAPSE", "HYPOTENSION",
]

EXCIPIENT = [
    "REACTION TO EXCIPIENT", "REACTION TO FOOD ADDITIVE",
    "REACTION TO PRESERVATIVES", "ALLERGY TO ARTHROPOD STING",
    "FOOD ALLERGY", "ALLERGY TO ANIMAL", "DRUG REACTION WITH EOSINOPHILIA",
    "GELATIN ALLERGY", "ALLERGY TO VACCINE",
]

# 复合终点：口腔/超敏切口
ORAL_HYP_COMPOSITE = sorted(
    set(CORE_ORAL + SENSORY + PHARYNGEAL_AIRWAY + SYSTEMIC_HYPER + EXCIPIENT)
)

PT_SETS = {
    "CORE_ORAL": CORE_ORAL,
    "SENSORY": SENSORY,
    "PHARYNGEAL_AIRWAY": PHARYNGEAL_AIRWAY,
    "SYSTEMIC_HYPER": SYSTEMIC_HYPER,
    "EXCIPIENT": EXCIPIENT,
}

# 严重性层级（用于机制解释与降级/升级分析）
SEVERITY_TIERS = {
    "tier1_local": ["CORE_ORAL", "SENSORY"],           # 局部黏膜/感觉
    "tier2_airway": ["PHARYNGEAL_AIRWAY"],             # 气道受累
    "tier3_systemic": ["SYSTEMIC_HYPER"],              # 全身超敏
}

# ---------------------------------------------------------------------------
# 3. 适应证 PT（用于指示证偏倚的敏感性分析，排除后重算）
# ---------------------------------------------------------------------------
INDICATION_PTS = [
    "MIGRAINE", "MIGRAINE WITH AURA", "MIGRAINE WITHOUT AURA", "MIGRAINE PROPHYLAXIS",
    "HEADACHE", "TENSION HEADACHE", "SINUS HEADACHE", "CLUSTER HEADACHE",
    "NAUSEA", "VOMITING", "PHOTOPHOBIA", "PHONOPHOBIA", "VERTIGO",
]

# ---------------------------------------------------------------------------
# 4. 工具函数
# ---------------------------------------------------------------------------
import re
from typing import Iterable, Set

_WS = re.compile(r"\s+")


def normalize(pt: str) -> str:
    """MedDRA PT 规范化：去多余空白、统一大写、处理连字符差异。"""
    if not isinstance(pt, str):
        return ""
    s = _WS.sub(" ", pt.strip().upper())
    s = s.replace("OEDEMA", "OEDEMA")  # 保留英式拼写，仅为可读性占位
    return s


def build_lookup() -> dict:
    """返回 {normalized_pt: [subset_name, ...]} 的多对多映射。"""
    lut: dict = {}
    for name, pts in PT_SETS.items():
        for p in pts:
            lut.setdefault(normalize(p), []).append(name)
    return lut


COMPOSITE_SET: Set[str] = {normalize(p) for p in ORAL_HYP_COMPOSITE}
INDICATION_SET: Set[str] = {normalize(p) for p in INDICATION_PTS}


def subset_of(pt: str) -> list:
    return [k for k, v in PT_SETS.items() if normalize(pt) in {normalize(x) for x in v}]
