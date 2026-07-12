"""
Risk assessment logic based on 3 fundamental dimensions.
Source: 5 academic papers on stock crash risk prediction.
"""


def assess_risk(pledge_status, em_level, big4_audit):
    has_pledge = "质押" in str(pledge_status) and pledge_status != "未质押"
    just_released = "刚解押" in str(pledge_status)
    high_em = em_level == "高"
    non_big4 = big4_audit == "否"

    if just_released and high_em and non_big4:
        return 5, "极高", "刚解押+高盈余管理+非四大审计=暴跌风险组合(谢德仁+潘越+辛清泉)"

    if just_released and (high_em or non_big4):
        return 4, "高", "刚解押+信息质量差(高盈余管理或非四大)(谢德仁论文:解押后风险显著上升)"

    if has_pledge and high_em:
        return 3, "高", "质押中+高盈余管理=维稳不可持续，风险积累"

    if has_pledge and non_big4:
        return 3, "高", "质押中+非四大审计=信息质量无保障"

    if just_released:
        return 3, "中高", "刚解押状态(解押后崩盘风险上升)"

    if high_em and non_big4:
        return 3, "中高", "高盈余管理+非四大=信息不透明(潘越论文:不透明->暴跌)"

    if high_em:
        return 2, "中", "高盈余管理=信息透明度低"

    if non_big4 and em_level == "中":
        return 2, "中", "非四大+中等盈余管理=信息质量一般"

    if not has_pledge and em_level == "低" and big4_audit == "是":
        return 1, "极低", "未质押+低盈余管理+四大审计=信息环境良好"

    return 2, "中", "常规状态"


def risk_label(level):
    stars = "*" * level
    names = {1: "极低", 2: "中", 3: "高", 4: "高", 5: "极高"}
    return f"{stars} {names.get(level, '未知')}"


def is_red_alert(pledge_status, em_level, big4_audit):
    if pledge_status in ("高比例", "刚解押"):
        return True
    if em_level == "高" and big4_audit == "否":
        return True
    return False


def is_green(pledge_status, em_level, big4_audit):
    return (
        pledge_status in ("未质押", "低比例")
        and em_level == "低"
        and big4_audit == "是"
    )
