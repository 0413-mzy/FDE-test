import examples from "./core-contexts.json";

export const cases = examples.cases;
export const scenarioLabels: Record<
  string,
  { title: string; subtitle: string }
> = {
  NORMAL: { title: "包裹运输进度", subtitle: "单包裹 · 来源完整" },
  MULTI_PARCEL: { title: "拆单后的包裹进度", subtitle: "两个包裹 · 状态不同" },
  STALE: { title: "物流记录很久没更新", subtitle: "历史记录 · 需说明时效" },
  SOURCE_FAILURE: {
    title: "部分包裹暂时无法查询",
    subtitle: "局部超时 · 保留已知事实",
  },
  UNKNOWN_TIME: {
    title: "来源更新时间未知",
    subtitle: "时间缺失 · 不能视为实时",
  },
  CONFLICT: {
    title: "仓库与物流信息不一致",
    subtitle: "来源冲突 · 需人工核实",
  },
};
export const draftSamples: Record<string, string> = {
  NORMAL:
    "根据 2026-09-20 05:50 UTC 的物流记录，您的包裹当时在运输中。我们暂时无法保证具体送达日期。",
  MULTI_PARCEL:
    "您的订单有两个包裹。根据 2026-09-20 05:50 UTC 的记录，第一个包裹在运输中，第二个包裹尚未揽收。两个包裹的进度不同，暂时无法保证送达日期。",
  STALE:
    "根据 2026-09-17 06:00 UTC 的物流记录，包裹当时在运输中。这份记录较旧，不能据此确认目前的位置，需要进一步核实最新进度。",
  SOURCE_FAILURE:
    "根据已取得的记录，第一个包裹当时在运输中。第二个包裹的物流查询超时，暂无法核实它的最新进度；查询失败本身不表示包裹发生物流异常。",
  UNKNOWN_TIME:
    "来源记录显示包裹有运输记录，但部分来源未提供更新时间，无法确认这些信息是否反映最新情况。暂时不能保证具体送达日期。",
  CONFLICT:
    "仓库备注与物流记录的信息存在冲突：仓库备注说今天尚未交给承运商，物流记录显示已揽收。目前无法确定哪一条准确，需要人工核实后再确认。",
};
export function utcLabel(value: string | null): string {
  return value ? value.replace("T", " ").replace("Z", " UTC") : "更新时间未知";
}
export const flagLabels: Record<string, string> = {
  STALE_DATA: "记录较旧",
  UNKNOWN_FRESHNESS: "更新时间未知",
  PARTIAL_SOURCE_FAILURE: "部分来源查询失败",
  MISSING_INFORMATION: "信息缺失",
  CONFLICTING_SOURCES: "来源信息冲突",
  UNKNOWN_STATUS: "未知业务状态",
  CLOCK_ANOMALY: "时间记录异常",
};
export const outcomeLabels: Record<string, string> = {
  SUCCESS: "查询成功",
  EMPTY: "查询成功 · 无记录",
  TIMEOUT: "查询超时",
  UNAVAILABLE: "来源不可用",
  NOT_FOUND: "来源记录不存在",
  NO_TRACKING: "未提供物流号",
  INVALID_RESPONSE: "返回数据无效",
  REJECTED: "来源拒绝查询",
  CONFLICT: "来源请求冲突",
};
