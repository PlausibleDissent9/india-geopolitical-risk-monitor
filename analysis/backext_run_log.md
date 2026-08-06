== backext run Thu Aug  6 11:34:24 UTC 2026 FAILED ==
  File "/home/runner/work/india-geopolitical-risk-monitor/india-geopolitical-risk-monitor/src/back_extension.py", line 92, in build
    df = client.query(q, job_config=cfg).to_dataframe()
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/cloud/bigquery/job/query.py", line 2194, in to_dataframe
    query_result = wait_for_query(self, progress_bar_type, max_results=max_results)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/cloud/bigquery/_tqdm_helpers.py", line 107, in wait_for_query
    return query_job.result(max_results=max_results)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/cloud/bigquery/job/query.py", line 1797, in result
    while not is_job_done():
              ^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/api_core/retry/retry_unary.py", line 294, in retry_wrapped_func
    return retry_target(
           ^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/api_core/retry/retry_unary.py", line 156, in retry_target
    next_sleep = _retry_error_helper(
                 ^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/api_core/retry/retry_base.py", line 216, in _retry_error_helper
    raise final_exc from source_exc
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/api_core/retry/retry_unary.py", line 147, in retry_target
    result = target()
             ^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/google/cloud/bigquery/job/query.py", line 1746, in is_job_done
    raise job_failed_exception
google.api_core.exceptions.InternalServerError: 500 Query exceeded limit for bytes billed: 20000000000. 22253928448 or higher required.; reason: bytesBilledLimitExceeded, message: Query exceeded limit for bytes billed: 20000000000. 22253928448 or higher required.

Location: US
Job ID: d1796bf5-c193-4206-a1d3-282f4229d195

