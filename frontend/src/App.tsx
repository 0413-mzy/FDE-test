import { useState } from "react";
import {
  cases,
  draftSamples,
  flagLabels,
  outcomeLabels,
  scenarioLabels,
  utcLabel,
} from "./fixtures";
import "./styles.css";

type PreviewState = "ready" | "loading" | "empty" | "error";

function ParcelIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 0v9m9-4-9 4-9-4m9 4v9M7.5 5.5l9 5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [selected, setSelected] = useState(0);
  const [previewState, setPreviewState] = useState<PreviewState>("ready");
  const [panel, setPanel] = useState<"evidence" | "sources">("evidence");
  const [editedDrafts, setEditedDrafts] = useState<Record<string, string>>({});
  const item = cases[selected];
  const context = item.context;
  const scenario = scenarioLabels[item.name];
  const draft = editedDrafts[item.name] ?? draftSamples[item.name];
  const changed = draft !== draftSamples[item.name];
  const findEvidence = (id: string | null) =>
    context.evidence.find((e) => e.id === id);
  const orderStatus = findEvidence(context.order.status_evidence_id);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="演示咨询列表">
        <div className="brand">
          <span className="brand-mark">
            <ParcelIcon />
          </span>
          <div>
            订单咨询助手<small>Order Support</small>
          </div>
        </div>
        <div className="sidebar-heading">
          <h2>咨询工作台</h2>
          <span className="count">{cases.length}</span>
        </div>
        <p className="sidebar-caption">虚构咨询 · 本地预览</p>
        <nav className="inquiry-list" aria-label="选择咨询场景">
          {cases.map((entry, index) => (
            <button
              type="button"
              key={entry.name}
              className={`inquiry-card ${selected === index ? "selected" : ""}`}
              aria-current={selected === index ? "true" : undefined}
              onClick={() => {
                setSelected(index);
                setPreviewState("ready");
                setPanel("evidence");
              }}
            >
              <span className="inquiry-card-top">
                <span>{entry.context.order.external_order_id}</span>
                <span
                  className={`dot ${entry.context.quality === "COMPLETE" ? "green" : "amber"}`}
                />
              </span>
              <strong>{scenarioLabels[entry.name].title}</strong>
              <small>{scenarioLabels[entry.name].subtitle}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="avatar">A</span>
          <div>
            示例客服<small>演示数据，无真实身份会话</small>
          </div>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <span>
            工作台 <span className="slash">/</span> 订单咨询
          </span>
          <span className="preview-badge">演示预览</span>
        </header>
        <div className="workspace-inner">
          <div className="page-heading">
            <div>
              <p className="eyebrow">ORDER SUPPORT WORKSPACE</p>
              <h1>{scenario.title}</h1>
              <p>
                {context.order.external_order_id}
                <span className="separator">·</span>Context v
                {context.context_version}
                <span className="separator">·</span>未审核
              </p>
            </div>
            <label className="state-picker">
              预览状态
              <select
                aria-label="预览状态"
                value={previewState}
                onChange={(e) =>
                  setPreviewState(e.target.value as PreviewState)
                }
              >
                <option value="ready">资料就绪</option>
                <option value="loading">加载中</option>
                <option value="empty">空列表</option>
                <option value="error">读取失败</option>
              </select>
            </label>
          </div>
          <div className="demo-notice">
            当前使用虚构数据。草稿编辑仅保存在本页，不会保存到服务端或发送给客户。
          </div>
          {previewState === "loading" && (
            <section className="state-card" role="status" aria-live="polite">
              <div className="loading-ring" />
              <h2>正在加载咨询资料</h2>
              <p>订单、包裹与来源记录加载后将在这里显示。</p>
            </section>
          )}
          {previewState === "empty" && (
            <section className="state-card">
              <span className="state-icon">
                <ParcelIcon />
              </span>
              <h2>暂无待处理咨询</h2>
              <p>咨询列表为空不表示来源查询失败。</p>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPreviewState("ready")}
              >
                返回演示咨询
              </button>
            </section>
          )}
          {previewState === "error" && (
            <section className="state-card" role="alert">
              <span className="state-symbol">!</span>
              <h2>暂时无法读取咨询资料</h2>
              <p>此状态是读取失败，不能据此判断订单或包裹发生异常。</p>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPreviewState("ready")}
              >
                返回演示咨询
              </button>
            </section>
          )}
          {previewState === "ready" && (
            <>
              <section
                className="question-card"
                aria-labelledby="question-title"
              >
                <span className="question-avatar">客</span>
                <div>
                  <div className="card-meta">
                    <h2 id="question-title">客户问题</h2>
                    <time dateTime={context.question.created_at}>
                      {utcLabel(context.question.created_at)}
                    </time>
                  </div>
                  <p>{context.question.text}</p>
                </div>
              </section>
              <div className="workbench-grid">
                <section className="facts-column" aria-labelledby="facts-title">
                  <div className="section-heading">
                    <h2 id="facts-title">订单资料与证据</h2>
                    <span
                      className={`quality-tag ${context.quality === "COMPLETE" ? "complete" : ""}`}
                    >
                      {context.quality === "COMPLETE"
                        ? "资料完整"
                        : "需注意数据质量"}
                    </span>
                  </div>
                  <div className="panel-switch" aria-label="资料视图">
                    <button
                      type="button"
                      aria-pressed={panel === "evidence"}
                      className={panel === "evidence" ? "active" : ""}
                      onClick={() => setPanel("evidence")}
                    >
                      业务证据
                    </button>
                    <button
                      type="button"
                      aria-pressed={panel === "sources"}
                      className={panel === "sources" ? "active" : ""}
                      onClick={() => setPanel("sources")}
                    >
                      来源查询
                    </button>
                  </div>
                  {panel === "sources" ? (
                    <div className="source-panel">
                      <p className="panel-hint">
                        成功空结果、记录不存在与查询失败分别展示。
                      </p>
                      <ul className="source-list">
                        {context.source_outcomes.map((source) => (
                          <li key={source.fetch_id}>
                            <div>
                              <strong>{source.operation}</strong>
                              <small>{source.target_id}</small>
                            </div>
                            <span
                              className={`source-result ${["SUCCESS", "EMPTY"].includes(source.outcome) ? "success" : "failure"}`}
                            >
                              {outcomeLabels[source.outcome] ?? source.outcome}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <>
                      <article className="order-card">
                        <div className="card-meta">
                          <h3>订单源记录</h3>
                          <span className="source-tag">OMS</span>
                        </div>
                        <div className="order-status">
                          <span>源状态</span>
                          <strong>
                            {String(orderStatus?.value ?? "未知")}
                          </strong>
                        </div>
                        <p className="timestamp">
                          源更新：
                          {utcLabel(orderStatus?.source_updated_at ?? null)}
                        </p>
                      </article>
                      <div className="parcel-section">
                        <div className="subheading">
                          <h3>包裹物流</h3>
                          <span>
                            {context.parcels.length} 个包裹 · 逐项查看
                          </span>
                        </div>
                        {context.parcels.map((parcel, index) => {
                          const shipment = findEvidence(
                            parcel.shipment_status_evidence_id,
                          );
                          const tracking = findEvidence(
                            parcel.tracking_number_evidence_id,
                          );
                          const outcome = context.source_outcomes.find(
                            (source) =>
                              source.operation === "get_shipment" &&
                              source.target_id === parcel.parcel_id,
                          );
                          return (
                            <article
                              className="parcel-card"
                              key={parcel.parcel_id}
                            >
                              <div className="parcel-heading">
                                <span className="parcel-icon">
                                  <ParcelIcon />
                                </span>
                                <div>
                                  <h4>包裹 {index + 1}</h4>
                                  <small>{parcel.parcel_id}</small>
                                </div>
                                <span
                                  className={`status-tag ${shipment ? "" : "uncertain"}`}
                                >
                                  {shipment
                                    ? String(shipment.value)
                                    : (outcomeLabels[outcome?.outcome ?? ""] ??
                                      "状态未知")}
                                </span>
                              </div>
                              <dl>
                                <div>
                                  <dt>物流单号</dt>
                                  <dd>
                                    {tracking
                                      ? String(tracking.value)
                                      : "未提供"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>源更新时间</dt>
                                  <dd>
                                    {shipment
                                      ? utcLabel(shipment.source_updated_at)
                                      : "未取得物流记录"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>抓取时间</dt>
                                  <dd>
                                    {shipment
                                      ? utcLabel(shipment.fetched_at)
                                      : "查询失败无事实抓取时间"}
                                  </dd>
                                </div>
                              </dl>
                              {shipment?.freshness_status === "STALE" && (
                                <p className="inline-warning">
                                  这份物流记录较旧，不能代表实时位置。
                                </p>
                              )}
                              {!shipment && (
                                <p className="inline-warning">
                                  暂无法核实该包裹；查询失败本身不表示物流异常。
                                </p>
                              )}
                              <div className="event-line">
                                <span className="timeline-dot" />
                                <div>
                                  <span className="event-label">
                                    已取得的事件记录
                                  </span>
                                  {parcel.event_evidence_ids.map((id) => {
                                    const event = findEvidence(id);
                                    return (
                                      <p key={id}>
                                        {String(event?.value ?? "未知")}
                                        <small>
                                          {utcLabel(event?.occurred_at ?? null)}
                                        </small>
                                      </p>
                                    );
                                  })}
                                  {parcel.event_evidence_ids.length === 0 && (
                                    <p>没有可展示的事件证据</p>
                                  )}
                                </div>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                      <article className="warehouse-card">
                        <div className="card-meta">
                          <h3>仓库备注</h3>
                          <span className="source-tag">来源原文</span>
                        </div>
                        {context.source_texts.map((id) => {
                          const note = findEvidence(id);
                          return (
                            <div key={id}>
                              <blockquote>
                                {String(note?.value ?? "")}
                              </blockquote>
                              <p className="timestamp">
                                源更新：
                                {utcLabel(note?.source_updated_at ?? null)}
                              </p>
                              <p className="raw-note-hint">
                                原文属于来源信息；计划与说明不等于已发生的业务动作。
                              </p>
                            </div>
                          );
                        })}
                      </article>
                    </>
                  )}
                  {context.risk_flags.length > 0 && (
                    <aside
                      className="quality-panel"
                      aria-labelledby="quality-title"
                    >
                      <h3 id="quality-title">数据质量与核实事项</h3>
                      <div className="flag-list">
                        {context.risk_flags.map((flag) => (
                          <span key={flag}>{flagLabels[flag] ?? flag}</span>
                        ))}
                      </div>
                      {context.missing_information.map((missing) => (
                        <p key={missing.code + missing.scope}>
                          {missing.scope}：
                          {missing.code === "SOURCE_TIMEOUT"
                            ? "物流查询超时，暂无法核实"
                            : missing.code}
                        </p>
                      ))}
                      {context.conflicts.map((conflict) => (
                        <div key={conflict.id}>
                          <p>{conflict.explanation}</p>
                          <ul>
                            {conflict.evidence_ids.map((id) => {
                              const e = findEvidence(id);
                              return (
                                <li key={id}>
                                  <strong>{e?.source_system}</strong>：
                                  {String(e?.value ?? "")}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      ))}
                    </aside>
                  )}
                </section>
                <aside className="draft-column" aria-labelledby="draft-title">
                  <div className="draft-card">
                    <div className="section-heading">
                      <h2 id="draft-title">回复草稿</h2>
                      <span className="draft-badge">
                        {changed ? "已修改预览" : "示例文本"}
                      </span>
                    </div>
                    <p className="draft-caption">
                      整理解释，保持事实、计划和不确定性清晰。
                    </p>
                    <label htmlFor="reply-preview" className="editor-label">
                      回复内容
                    </label>
                    <textarea
                      id="reply-preview"
                      value={draft}
                      maxLength={10000}
                      onChange={(e) =>
                        setEditedDrafts({
                          ...editedDrafts,
                          [item.name]: e.target.value,
                        })
                      }
                    />
                    <div className="editor-footer">
                      <span>{draft.length} / 10000</span>
                      <button
                        type="button"
                        onClick={() =>
                          setEditedDrafts({
                            ...editedDrafts,
                            [item.name]: draftSamples[item.name],
                          })
                        }
                        disabled={!changed}
                      >
                        恢复示例
                      </button>
                    </div>
                    <div className="validation-notice">
                      <span className="validation-mark">○</span>
                      <div>
                        <strong>尚未执行校验</strong>
                        <p>编辑后的文本也需要重新校验，再由客服审核。</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="approve-button"
                      disabled
                      aria-describedby="approval-hint"
                    >
                      批准草稿
                    </button>
                    <p id="approval-hint" className="approval-hint">
                      此预览不执行批准或发送。
                    </p>
                  </div>
                  <div className="review-card">
                    <h3>人工审核时请确认</h3>
                    <ul>
                      <li>重要声明能追溯到来源与时间</li>
                      <li>没有将计划、旧数据说成最新事实</li>
                      <li>冲突、缺失与查询失败得到说明</li>
                      <li>没有保证履约或声称高风险动作已执行</li>
                    </ul>
                    <p>程序负责事实，AI 负责解释与措辞。</p>
                  </div>
                </aside>
              </div>
            </>
          )}
          <footer className="workspace-footer">
            虚构示例 · 时间以 UTC 展示 · 人工审核是最终边界
          </footer>
        </div>
      </main>
    </div>
  );
}
