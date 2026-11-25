import datetime as dt
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
FIXED_TIME='2026-11-25T12:00:00'
class FixedDatetime(dt.datetime):
    @classmethod
    def now(cls,tz=None):
        value=cls(2026,11,25,12,0,0)
        return value if tz is None else value.replace(tzinfo=dt.timezone.utc).astimezone(tz)
class ModuleProxy:
    datetime=FixedDatetime
    def __getattr__(self,name):return getattr(dt,name)
@contextmanager
def environment_clock():
    from agentdojo.default_suites.v1.tools import email_client,cloud_drive_client
    with ExitStack() as stack:
        for module in [email_client,cloud_drive_client]:stack.enter_context(patch.object(module,'datetime',ModuleProxy()))
        yield
