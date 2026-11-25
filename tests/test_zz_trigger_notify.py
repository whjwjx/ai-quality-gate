"""临时文件：故意失败以触发飞书告警，验证链路后删除。"""


def test_deliberate_failure_to_trigger_alert():
    assert False, "这是为了验证告警链路而故意制造的失败"
