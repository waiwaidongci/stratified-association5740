import csv,io
from sqlalchemy import select
from fastapi import HTTPException
from src.models import VerificationNote,AssociationRun
from src.constants.enums import NoteStatus
from src.utils.audit import record
from src.utils.serializers import serialize
def listing(db):return [serialize(x) for x in db.scalars(select(VerificationNote).order_by(VerificationNote.id.desc()))]
def create(db,data,user):
    run=db.get(AssociationRun,data.run_id)
    if not run:raise HTTPException(404,'研究不存在')
    if run.status!='completed':raise HTTPException(409,'仅已完成研究可形成复验说明')
    if db.scalar(select(VerificationNote).where(VerificationNote.title==data.title)):raise HTTPException(409,'说明名称重复')
    note=VerificationNote(**data.model_dump(),created_by=user.id);db.add(note);db.flush();record(db,user,'note.created',note.id);db.commit();return serialize(note)
def review(db,id,data,user):
    note=db.get(VerificationNote,id)
    if not note:raise HTTPException(404,'复验说明不存在')
    if note.status!=NoteStatus.DRAFT:raise HTTPException(409,'复验说明已审阅')
    note.status=NoteStatus(data.decision);note.review_comment=data.comment;note.approved_by=user.email;record(db,user,'note.'+data.decision,id);db.commit();return serialize(note)
def export(db,id,user):
 note=db.get(VerificationNote,id)
 if not note:raise HTTPException(404,'复验说明不存在')
 if note.status!=NoteStatus.APPROVED:raise HTTPException(403,'仅已批准说明可导出')
 run=db.get(AssociationRun,note.run_id);r=run.result;out=io.StringIO();w=csv.writer(out)
 if r.get('run_type')=='interval_scan':
  scan=r['interval_scan']
  w.writerow(['note','method','fingerprint','alpha','scan_type','layer_count','observed_statistic','observed_statistic_scaled','scale_lcm','global_tail_p','global_tail_p_log','global_tail_underflow','below_alpha','selected_window_count','interpretation','action','boundary'])
  w.writerow([note.title,r['method_version'],r['fingerprint'],r['alpha'],scan['scan_type'],scan['layer_count'],scan['observed_statistic'],scan['observed_statistic_scaled'],scan['scale_lcm'],scan['global_tail_p_display'],scan['global_tail_p_log'],scan['global_tail_p_underflow'],scan['below_alpha'],scan['selected_window_count'],note.interpretation,note.action,r['interpretation']])
  w.writerow(['frozen_layer_order_index','code','name'])
  for layer in scan['layer_order']:w.writerow([layer['index'],layer['code'],layer['name']])
  w.writerow(['selected_window','start_layer_index','end_layer_index','start_layer_code','end_layer_code','layer_count','deviation_numerator','deviation_denominator','deviation_value'])
  for win in scan['selected_windows']:w.writerow([f"{win['start_layer_index']+1}..{win['end_layer_index']+1}",win['start_layer_index'],win['end_layer_index'],win['start_layer_code'],win['end_layer_code'],win['layer_count'],win['deviation_numerator'],win['deviation_denominator'],win['deviation_value']])
  w.writerow(['layer','observed_a','mean_numerator','mean_denominator','scaled_deviation','support_lower','support_upper','support_count'])
  for d in scan['layer_deviations']:w.writerow([d['code'],d['observed_a'],d['mean_numerator'],d['mean_denominator'],d['scaled_deviation'],d['support_lower'],d['support_upper'],d['support_count']])
  w.writerow(['scan_statistic_t_scaled','t_value','probability','log_probability','included_global_tail'])
  for d in scan['statistic_distribution']:w.writerow([d['t_scaled'],d['t_value'],d['probability'],d['log_probability'],d['in_tail']])
  record(db,user,'note.exported',id);db.commit();return out.getvalue()
 w.writerow(['note','method','fingerprint','alpha','adjusted_or_status','adjusted_or','cmh','asymptotic_p','asymptotic_p_log','exact_p','exact_p_log','interpretation','action','boundary'])
 w.writerow([note.title,r['method_version'],r['fingerprint'],r['alpha'],r['adjusted_or']['status'],r['adjusted_or']['value'],r['cmh'],r['asymptotic_p_display'],r['asymptotic_p_log'],r['exact']['p_display'],r['exact']['p_log'],note.interpretation,note.action,r['interpretation']])
 w.writerow(['stratum','a_A_success','b_A_fail','c_B_success','d_B_fail','rate_A','rate_B','OR_status','OR','expected_a','variance_a'])
 for t in r['strata']:w.writerow([t['code'],t['a'],t['b'],t['c'],t['d'],t['rate_a'],t['rate_b'],t['odds_ratio']['status'],t['odds_ratio']['value'],t['expected_a'],t['variance_a']])
 w.writerow(['exact_support_s','probability','log_probability','included_mean_distance_tail'])
 for d in r['exact']['distribution']:w.writerow([d['s'],d['probability'],d['log_probability'],d['in_tail']])
 record(db,user,'note.exported',id);db.commit();return out.getvalue()
