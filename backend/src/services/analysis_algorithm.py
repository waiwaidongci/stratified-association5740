import hashlib,json,math
from .cmh_algorithm import calculate_cmh
from .exact_algorithm import exact_test
from .interval_scan_algorithm import interval_scan_test

RUN_TYPE_LAYERWISE='layerwise_exact'
RUN_TYPE_INTERVAL_SCAN='interval_scan'
RUN_TYPES=(RUN_TYPE_LAYERWISE,RUN_TYPE_INTERVAL_SCAN)

def analyze(snapshot,alpha,run_type=RUN_TYPE_LAYERWISE):
 if isinstance(alpha,bool) or not isinstance(alpha,(int,float)) or not math.isfinite(alpha) or not .001<=alpha<=.1:raise ValueError('alpha须在.001..0.1之间')
 if run_type not in RUN_TYPES:raise ValueError('未知研究类型')
 tables=sorted(snapshot['tables'],key=lambda t:t['code']);cmh=calculate_cmh(tables)
 if run_type==RUN_TYPE_INTERVAL_SCAN:
  scan=interval_scan_test(cmh['strata'],alpha)
  canonical={'version':'frozen-interval-scan-exact-v1','run_type':run_type,'snapshot':{**snapshot,'tables':tables},'alpha':alpha}
  fingerprint=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  return {**cmh,'interval_scan':scan,'run_type':run_type,'alpha':alpha,'input_snapshot':canonical['snapshot'],'fingerprint':fingerprint,'method_version':canonical['version'],'interpretation':'区间扫描在预先声明、顺序冻结的湿度层上枚举全部连续区间；全局精确尾在同一固定边际联合分布上计算，含并列，不是逐区间独立检验，也无模拟替代。扫描只回答条件零假设下区间最大偏离的罕见程度，不识别封装因果，层构成差异仍需独立试片复验。'}
 exact=exact_test(cmh['strata'],cmh['observed_sum_a'],alpha)
 canonical={'version':'cmh-mean-distance-exact-v1','run_type':run_type,'snapshot':{**snapshot,'tables':tables},'alpha':alpha}
 fingerprint=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 return {**cmh,'exact':exact,'run_type':run_type,'alpha':alpha,'input_snapshot':canonical['snapshot'],'fingerprint':fingerprint,'method_version':canonical['version'],'interpretation':'独立层内观察、固定边际条件零假设；精确p为均值距离双侧。共同OR仅加权汇总，未检验层间同质；分层关联不是封装效果的因果保证，稀疏表渐近p只作对照。'}
