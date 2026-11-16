<script setup lang="ts">import{computed}from 'vue';
import type{IntervalScan}from '../types/domain';
import{fmt}from '../utils/format';
const props=defineProps<{scan:IntervalScan}>();
const maxProb=computed(()=>Math.max(...props.scan.statistic_distribution.map(d=>d.probability),1e-300));
const span=computed(()=>{
 const d=props.scan.statistic_distribution;
 return {lo:d[0]?.t_scaled??0,hi:d[d.length-1]?.t_scaled??1,n:d.length};
});
const x=(t:number)=>42+(t-span.value.lo+.5)/Math.max(1,span.value.hi-span.value.lo+1)*820;
const bw=computed(()=>820/Math.max(1,span.value.n));
</script>
<template>
 <section class="interval-scan-sheet">
  <div class="section-heading">
   <h2>冻结层顺序上的连续区间扫描</h2>
   <span>{{scan.layer_count}}层 / 枚举{{scan.support_compositions.toLocaleString()}}个可达条件组合 / 峰值{{scan.peak_states.toLocaleString()}}状态</span>
  </div>
  <div class="scan-totals">
   <div><small>观察扫描统计量 T</small><b>{{scan.observed_statistic_numerator}}<span v-if="scan.observed_statistic_denominator!==1"> / {{scan.observed_statistic_denominator}}</span></b></div>
   <div><small>全局精确尾 P(T≥T观察)</small><b class="p-value">{{scan.global_tail_p_display}}</b></div>
   <div><small>取得最大值的连续区间</small><b>{{scan.selected_window_count}} 个（含并列）</b></div>
   <div><small>α = {{scan.alpha}} 判定</small><b :class="{'p-value':scan.below_alpha}">{{scan.below_alpha?'达到预设探索阈值':'未达到预设探索阈值'}}</b></div>
  </div>
  <p class="scan-rule">{{scan.statistic_rule}}</p>
  <p class="scan-rule">{{scan.tail_rule}}</p>
  <div class="table-wrap">
   <table>
    <thead><tr><th>选中区间</th><th>层范围</th><th>层数</th><th>区间偏离（有理数）</th><th>区间偏离（数值）</th></tr></thead>
    <tbody>
     <tr v-for="(w,i) in scan.selected_windows" :key="i">
      <td>{{w.start_layer_index+1}} .. {{w.end_layer_index+1}}</td>
      <td>{{w.start_layer_code}} → {{w.end_layer_code}}</td>
      <td>{{w.layer_count}}</td>
      <td>{{w.deviation_numerator}}<template v-if="w.deviation_denominator!==1"> / {{w.deviation_denominator}}</template></td>
      <td>{{fmt(w.deviation_value,8)}}</td>
     </tr>
    </tbody>
   </table>
  </div>
  <h3 class="ruled-title">冻结的层顺序与逐层偏离</h3>
  <div class="table-wrap">
   <table>
    <thead><tr><th>顺序</th><th>层</th><th>观察 a</th><th>条件均值 E[a]</th><th>缩放后偏离</th><th>超几何支持</th><th>支持点数</th></tr></thead>
    <tbody>
     <tr v-for="d in scan.layer_deviations" :key="d.code">
      <td>{{d.index+1}}</td>
      <td>{{d.code}}</td>
      <td>{{d.observed_a}}</td>
      <td>{{d.mean_numerator}}<template v-if="d.mean_denominator!==1"> / {{d.mean_denominator}}</template></td>
      <td :class="d.scaled_deviation<0?'neg':'pos'">{{d.scaled_deviation}}</td>
      <td>{{d.support_lower}} .. {{d.support_upper}}</td>
      <td>{{d.support_count}}</td>
     </tr>
    </tbody>
   </table>
  </div>
  <p class="scan-rule">整数缩放 L = {{scan.scale_lcm.toLocaleString()}}（各层条件均值约分分母的最小公倍数）；区间统计量在整数刻度上精确比较并列。质量合计 {{fmt(scan.probability_sum,12)}}。</p>
  <div class="distribution-scroll">
   <svg viewBox="0 0 930 330" role="img" :aria-label="'扫描统计量T的固定边际精确分布，共'+span.n+'个取值'">
    <line x1="42" y1="260" x2="862" y2="260" class="axis"/>
    <rect v-for="d in scan.statistic_distribution" :key="d.t_scaled" :x="x(d.t_scaled)-bw/2+.2" :y="260-d.probability/maxProb*200" :width="Math.max(.25,bw-.4)" :height="d.probability/maxProb*200" :class="d.in_tail?'tail-mass':'central-mass'">
     <title>T={{d.t_scaled}}, P={{d.probability}}, 入全局尾={{d.in_tail}}</title>
    </rect>
    <line :x1="x(scan.observed_statistic_scaled)" :x2="x(scan.observed_statistic_scaled)" y1="28" y2="260" class="observed-line"/>
    <text :x="Math.min(780,Math.max(42,x(scan.observed_statistic_scaled)+6))" y="22">观察 T（缩放）={{scan.observed_statistic_scaled}}</text>
    <text x="42" y="286">{{span.lo}}</text>
    <text x="820" y="286">{{span.hi}}</text>
    <text x="320" y="314">扫描统计量 T（整数刻度）/ 固定边际联合分布</text>
   </svg>
  </div>
  <p class="plot-caption"><i class="tail-key"/>砖红点纳入全局精确尾；每根柱为 T 的一个取值。尾概率在全部层超几何乘积分布上枚举，含并列，非模拟。</p>
  <details>
   <summary>逐个统计量取值的概率、log与全局尾归属</summary>
   <div class="table-wrap exact-mass-table">
    <table>
     <thead><tr><th>T（缩放）</th><th>T（原值）</th><th>概率</th><th>log概率</th><th>入全局尾</th></tr></thead>
     <tbody>
      <tr v-for="d in scan.statistic_distribution" :key="d.t_scaled">
       <td>{{d.t_scaled}}</td>
       <td>{{fmt(d.t_value,6)}}</td>
       <td>{{d.probability.toExponential(8)}}</td>
       <td>{{fmt(d.log_probability,8)}}</td>
       <td>{{d.in_tail?'是':'否'}}</td>
      </tr>
     </tbody>
    </table>
   </div>
  </details>
  <p class="scan-rule">内存守卫：干跑估计峰值 {{scan.estimated_memory_mib}} MiB，限额 {{(scan.memory_limit_bytes/1048576).toFixed(0)}} MiB；预计超限即在加权枚举前拒绝计算。{{scan.numeric}}</p>
 </section>
</template>
