"""scripts 测试脚本公共模块：每次运行生成一个 uuid 作为 request_id。

放在 app 包（正规 Python 包）内，PyCharm 可直接识别：
    from app.common import REQUEST_ID
"""
import uuid

REQUEST_ID = uuid.uuid4().hex
