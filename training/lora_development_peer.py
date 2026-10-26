"""One-shot model peer for the new development package; injected providers only.

This component never loads weights or grants permission. The approved worker
must establish source/assets, resource supervision and fixed state ownership.
Raw outputs are written before post-generation checks; uncertainty is sticky.
"""
from __future__ import annotations

import threading

from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_rhino_adapter import invoke_step
from training.c5_formal20_privacy import allowed
from training.lora_development_wire import (check_predecessor, detached, model_response,
    reparse_response, user_step, validate_request)


class DevelopmentPeer:
    def __init__(self, *, state, runtime, views, identities, tokenizer, generate, route_context, guard):
        self.state, self.runtime, self.views, self.identities = state, runtime, detached(views), detached(identities)
        self.tokenizer, self.generate, self.route_context, self.guard = tokenizer, generate, route_context, guard
        self.blocked, self.lock = False, threading.Lock()

    def infer(self, request):
        require(self.lock.acquire(blocking=False), "concurrent model request refused")
        try:
            require(not self.blocked, "uncertain peer refuses further generation")
            sent = validate_request(request, self.views, self.runtime)
            key = digest({"slot_id": sent["slot_id"], "step_index": sent["step_index"], "runtime": self.runtime})
            if sent["step_index"]:
                previous_key = digest({"slot_id": sent["slot_id"], "step_index": sent["step_index"] - 1,
                                       "runtime": self.runtime})
                previous = read_json(self.state, previous_key + ".response.json")
                prior_request = read_json(self.state, previous_key + ".request.json")
                check_predecessor(sent, prior_request, previous["observation"])
            else:
                check_predecessor(sent, None, None)
            self.guard()
            # This exclusive request persists before any generation, including
            # in a newly constructed peer using the same approved state root.
            publish_json(self.state, key + ".request.json", sent)
            self.blocked = True
            generations = []
            def generate(prompt, stage):
                retained = False
                self.guard()
                publish_json(self.state, key + "." + stage + ".intent.json",
                             {"stage": stage, "request_sha256": digest(sent)})
                try:
                    value = self.generate(prompt, stage)
                    require(type(value) is dict, "raw model return missing")
                    row = {"stage": stage, **value}
                    publish_json(self.state, key + "." + stage + ".raw.json", row)
                    retained = True
                    generations.append(row)
                    self.guard()
                    return value
                except BaseException as exc:
                    publish_json(self.state, key + "." + stage + ".failure.json",
                                 {"error_type": type(exc).__name__, "raw_return_retained": retained})
                    raise
            rendered = user_step(sent)
            with self.route_context(sent["route"]):
                observed = invoke_step(self.tokenizer, generate, rendered, scene_binding=sent["binding"],
                    privacy_guard=lambda text: text == rendered and allowed(sent["task"], sent["scene"]))
            self.guard()
            result = model_response(sent, observed, generations, self.identities[sent["route"]])
            publish_json(self.state, key + ".response.json", result)
            if observed["status"] != "operational_failure_no_retry":
                reparse_response(result, sent, model_views=self.views, runtime=self.runtime,
                                 identity=self.identities[sent["route"]], tokenizer=self.tokenizer)
                self.blocked = False
            return result
        except BaseException:
            self.blocked = True
            raise
        finally:
            self.lock.release()
