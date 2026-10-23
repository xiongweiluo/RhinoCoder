"""Worker-side selected-subset/order guard, before raw request claim/generation."""
from plugin.rhino_listener.c5_research_native import require

def validate_scheduled_request(sent,plans,order,indices,attempted):
 require(type(order) is list and len(order)==40 and {s['slot_id'] for s in order}==set(plans),'slot_worker_complete_order')
 require(type(indices) is list and indices==sorted(set(indices)) and all(type(i) is int and 0<=i<40 for i in indices),'slot_worker_indices')
 labels=[order[i]['slot_id'] for i in indices];slot=sent.get('slot_id')
 require(slot in labels,'slot_worker_outside_approved_subset')
 if not attempted or attempted[-1]!=slot:
  # Local fixture failure can have zero requests: later indices may be skipped,
  # but no prior index can be regenerated and no outside slot can be inserted.
  require(slot not in attempted and (not attempted or labels.index(slot)>labels.index(attempted[-1])),'slot_worker_replay_or_order')
  attempted.append(slot)
