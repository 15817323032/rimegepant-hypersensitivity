"""FAERS 年龄字段归一化 —— 唯一事实源（single source of truth）。

FAERS 的 DEMO.age 是纯数字，单位由 DEMO.age_cod 决定。粗放地
``pd.to_numeric(age)`` 会把 ``age=5, age_cod=DEC``（=50 岁）读成 5 岁，
把成人误判为儿童。表 1、表 5 与参照人群必须共用本函数，否则同一份
数据会出现两套年龄定义（2026-11 曾因此出现表 1 = 42 例、
表 5 = 85 例的 <18 矛盾）。

支持的单位（FAERS 官方 age_cod）：
    YR  年      DEC 十年     MON 月      WK  周      DY  天
以及 HR（小时）——本库未出现，但一并处理以防新季度引入。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 1 个单位折算为多少年
UNIT_TO_YEARS = {
    "YR": 1.0,
    "DEC": 10.0,
    "MON": 1.0 / 12.0,
    "WK": 1.0 / 52.1429,      # 365.25/7
    "DY": 1.0 / 365.25,
    "HR": 1.0 / (365.25 * 24),
}

DEFAULT_UNIT = "YR"
AGE_CAP = 120


def age_years(age, age_cod=None, cap: int = AGE_CAP) -> pd.Series:
    """把 ``age`` + ``age_cod`` 归一化为「岁」。

    Parameters
    ----------
    age : Series
        原始年龄值，可为字符串（FAERS 原始 txt 用 dtype=str 读入）。
    age_cod : Series, optional
        单位代码；缺失时按 ``YR`` 处理（FAERS 绝大多数记录如此）。
    cap : int
        合理上限，超出视为脏数据并置为 NaN。

    Returns
    -------
    Series[float64]
        以年为单位的年龄；无法解析、单位未知或超出 [0, cap] 者为 NaN。
    """
    a = pd.to_numeric(pd.Series(age), errors="coerce")

    if age_cod is None:
        cod = pd.Series(DEFAULT_UNIT, index=a.index)
    else:
        cod = (pd.Series(age_cod)
               .reindex(a.index)
               .fillna(DEFAULT_UNIT)
               .astype(str)
               .str.strip()
               .str.upper())

    out = pd.Series(np.nan, index=a.index, dtype="float64")
    for unit, factor in UNIT_TO_YEARS.items():
        m = cod.eq(unit)
        if m.any():
            out[m] = a[m] * factor

    return out.where(out.between(0, cap))


def age_group(age_yr: pd.Series, labels=("<18", "18-44", "45-64", ">=65")) -> pd.Series:
    """按归一化年龄分箱，边界与既往分析一致。

    用左闭右开区间：单位换算后会出现小数年龄（44.5 岁），若沿用
    ``pd.cut([...,44,64,200])``（左开右闭）这类值会落空，导致四档合计
    小于有记录例数。
    """
    return pd.cut(age_yr, [-0.001, 18, 45, 65, 200], right=False, labels=list(labels))
