import type { PaperCorporateEvent } from "../api/types";
import { dateInt, money } from "../lib/format";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import Panel from "./Panel";

export default function PaperCorporateEvents({ events, live }: { events: PaperCorporateEvent[]; live: boolean }) {
  return (
    <Panel title="公司行为调整" subtitle={live ? "实时模拟未接入公司行为事件流" : "历史回放 · 税前现金按除权日近似计入，实际到账日与税费未建模"}>
      {live ? <p className="page-note-sm">实时模拟不提供公司行为事件流；这里不展示历史调整记录。</p> : !events.length ? (
        <EmptyState compact title="暂无公司行为调整" hint="推进至持仓证券的公司行为日期后，会显示现金、股数与相关撤单记录；重置账户会清空记录。" />
      ) : (
        <ol role="list" aria-label="公司行为调整记录" className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {events.slice().reverse().map((event, index) => (
            <li className="stack-tight" key={`${event.date}:${event.sec_id}:${index}`}>
              <div className="row">
                <strong className="mono">{event.code}</strong>
                <Badge tone="neutral">{dateInt(event.date)}</Badge>
              </div>
              <div className="row">
                <span>现金变化 {event.cash > 0 ? "+" : ""}{money(event.cash)}</span>
                <span>股数 {event.qty_before.toLocaleString("zh-CN")} → {event.qty_after.toLocaleString("zh-CN")}</span>
              </div>
              {event.cancelled_order_ids.length ? (
                <details>
                  <summary>已撤销 {event.cancelled_order_ids.length} 笔相关委托</summary>
                  <p className="page-note-sm">相关委托的未成交部分已撤销；如需继续交易，请按调整后的股数与价格重新下单。</p>
                  <ul>{event.cancelled_order_ids.map((id) => <li className="mono-wrap" key={id}>{id}</li>)}</ul>
                </details>
              ) : null}
              {event.reason ? <details><summary>调整依据</summary><p className="page-note-sm mono-wrap">{event.model === "pre_tax_ex_date_approximation" ? "按除权前持股计入税前现金，再调整送转股数；旧委托的未成交部分撤销。实际到账延迟、分红税及零股现金权利未建模。" : event.reason}</p></details> : null}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
