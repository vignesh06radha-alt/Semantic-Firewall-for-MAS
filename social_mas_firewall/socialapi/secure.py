"""Social adapter: trusted IDs establish task scope, text never grants it."""
from copy import deepcopy

from security.runtime import Action, Permission, PolicyDenied, SecurityRuntime, TaskPolicy


def public_reply_policy(task_id, event, platform):
    matches = [c for c in platform.comments.get(event["post_id"], [])
               if c["id"] == event["comment_id"] and c["user"] == event["user"]]
    if len(matches) != 1 or event["post_id"] not in platform.posts:
        raise PolicyDenied("unverified_event")
    post, user = event["post_id"], event["user"]
    return TaskPolicy(task_id, (
        Permission("read_post", frozenset({post})),
        Permission("read_comments", frozenset({post})),
        Permission("read_profile", frozenset({user})),
        Permission("read_engagement", frozenset({post})),
        Permission("read_new_comments", frozenset({post})),
        Permission("reply", frozenset({post}), frozenset({user}), write=True),
    ))


class SecureSocialPlatform:
    """Only trusted application code receives this facade; no raw connector API."""
    def __init__(self, platform, ctx):
        self._platform = platform
        self._ctx = ctx

    @property
    def tool_calls(self):
        return self._ctx.security.reads + self._ctx.security.writes

    @property
    def actions(self):
        return deepcopy(self._platform.actions)

    def _read(self, operation, resource, fetch):
        result = self._ctx.security.execute(Action(operation, resource), fetch)
        self._ctx.record_source("tool:" + operation, result)
        return result

    def fetch_post(self, post):
        return self._read("read_post", post, lambda: self._platform.fetch_post(post))

    def fetch_comments(self, post):
        return self._read("read_comments", post, lambda: self._platform.fetch_comments(post))

    def fetch_profile(self, user):
        user = user.lstrip("@")
        return self._read("read_profile", user, lambda: self._platform.fetch_profile(user))

    def get_engagement(self, post):
        return self._read("read_engagement", post, lambda: self._platform.get_engagement(post))

    def drain_new_comments(self, post):
        return self._read("read_new_comments", post, lambda: self._platform.drain_new_comments(post))

    def execute_action(self, action):
        # Action is immutable and supplies the exact values used by the callback.
        def write():
            if action.operation == "reply":
                self._platform.publish_reply(action.resource, action.recipient, action.text)
            elif action.operation == "publish":
                self._platform.publish_post(action.text)
            elif action.operation == "dm":
                self._platform.send_dm(action.recipient, action.text)
            else:
                raise ValueError("Unknown social write")
            return self._platform.actions[-1]
        return self._ctx.security.execute(action, write, sources=self._ctx.source_ids)


def enable_security(ctx, event, policy=None):
    if ctx.security is not None:
        raise ValueError("Security is already configured")
    policy = policy or public_reply_policy(ctx.run_id, event, ctx.platform)
    if policy.task_id != ctx.run_id:
        raise PolicyDenied("task_mismatch")
    ctx.security = SecurityRuntime(policy)
    ctx.platform = SecureSocialPlatform(ctx.platform, ctx)
    ctx.record_source("external_event", event)
