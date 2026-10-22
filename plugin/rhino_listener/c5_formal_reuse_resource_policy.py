"""Rhino 3.9-safe formal resource contract; no clocks or effects on import."""
import math
from .c5_research_native import require

def validate_boundary(b):
    required={'owner_confirmed','provider_expiry_epoch','generation_cutoff_epoch','export_reserve_seconds',
        'formal_max_seconds','historical_cumulative_upper_bound_seconds','original_16_hour_compliance_claimed',
        'old_budget_recredited','unused_development_transferred_to_formal','development_first_load_epoch',
        'development_attempts_consumed','development_campaign_head_sha256','development_seconds_max',
        'research_cumulative_max_seconds','development_elapsed_to_release_seconds'}
    require(type(b) is dict and set(b)==required and b['owner_confirmed'] is True,'formal_reuse_resource_facts')
    require(all(type(b[k]) in (int,float) and math.isfinite(b[k]) and b[k]>0
        for k in ('provider_expiry_epoch','generation_cutoff_epoch','development_first_load_epoch'))
        and b['formal_max_seconds']==64800 and type(b['formal_max_seconds']) is int
        and b['export_reserve_seconds']==900 and type(b['export_reserve_seconds']) is int
        and b['provider_expiry_epoch']-b['generation_cutoff_epoch']==900,
        'formal_reuse_finite_resource_limits')
    require(b['historical_cumulative_upper_bound_seconds'] is None
        and all(b[k] is False for k in ('original_16_hour_compliance_claimed','old_budget_recredited',
            'unused_development_transferred_to_formal'))
        and b['development_attempts_consumed']==3
        and b['development_first_load_epoch']==1791916117.781239
        and b['development_campaign_head_sha256']=='ebb572fbbe53ea2ec5c5a191f56ea1ee7767eef7525eca69d4a8a56a90f1975a',
        'formal_reuse_original_timing_and_consumption_required')
    require(type(b['development_seconds_max']) is int and b['development_seconds_max']==86400
        and type(b['research_cumulative_max_seconds']) is int and b['research_cumulative_max_seconds']==151200
        and b['development_seconds_max']+b['formal_max_seconds']==b['research_cumulative_max_seconds']
        and type(b['development_elapsed_to_release_seconds']) in (int,float)
        and math.isfinite(b['development_elapsed_to_release_seconds'])
        and b['development_elapsed_to_release_seconds']==66773.24127721786
        and 0<=b['development_elapsed_to_release_seconds']<=b['development_seconds_max'],
        'formal_reuse_accepted_aggregate_resource_cap_and_actual_development_usage')
    return b

