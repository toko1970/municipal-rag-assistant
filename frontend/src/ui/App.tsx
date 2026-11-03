import { useEffect, useState, type FormEvent } from "react";
import { api, ApiClientError, type FeedbackValue, type QuestionResult } from "../api";

type ScreenState = "idle" | "submitting" | "success" | "degraded" | "error" | "processing";
type PendingSubmission = { key: string; state: "issuing" | "processing"; submitBy?: string; sessionExpiresAt?: string };
const STORAGE_KEY = "rag-demo-pending-submission-v1";
const FEEDBACK_VALUES: FeedbackValue[] = ["採用した", "修正して採用した", "採用しなかった"];
const unicodeLength = (value: string) => Array.from(value).length;
const feedbackLength = (value: string) => unicodeLength(value.normalize("NFC").replace(/\p{Cc}/gu, ""));

function makeIdempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function savePending(pending: PendingSubmission | null) {
  if (pending) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
  else sessionStorage.removeItem(STORAGE_KEY);
}

function loadPending(): PendingSubmission | null {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null") as PendingSubmission | null;
    return parsed && typeof parsed.key === "string" && parsed.key.length >= 43 ? parsed : null;
  } catch {
    return null;
  }
}

function describeError(error: unknown): string {
  if (!(error instanceof ApiClientError)) return "処理を完了できませんでした。時間を置いて再度お試しください。";
  switch (error.code) {
    case "QUOTA_QUESTION_SESSION":
    case "QUOTA_QUESTION_GLOBAL":
    case "QUOTA_KEY_SESSION":
    case "QUOTA_KEY_GLOBAL":
    case "QUOTA_FEEDBACK_SESSION":
    case "QUOTA_FEEDBACK_GLOBAL":
      return error.message || "利用上限に達しました。時間を置いてからお試しください。";
    case "IDEMPOTENCY_SLOT_BUSY":
      return "送信準備中の質問があります。ページを再読み込みして状態を確認してください.";
    case "SESSION_INVALID":
    case "SESSION_REQUIRED":
      return "セッションの有効期限が切れました。ページを再読み込みしてから質問してください。";
    default:
      return error.message;
  }
}

function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QuestionResult | null>(null);
  const [state, setState] = useState<ScreenState>("idle");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<PendingSubmission | null>(() => loadPending());
  const [feedback, setFeedback] = useState<FeedbackValue>(FEEDBACK_VALUES[0]);
  const [comment, setComment] = useState("");
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const [imageFailures, setImageFailures] = useState<string[]>([]);

  useEffect(() => {
    if (!pending || pending.state !== "processing") return;
    setState("processing");
    setMessage("前回の送信結果を確認できます。自動で再送はしません。");
  }, []);

  const applyResult = (value: QuestionResult) => {
    savePending(null);
    setPending(null);
    setResult(value);
    setState(value.degraded || value.answer_status !== "SUCCESS" ? "degraded" : "success");
    setMessage(value.degraded || value.answer_status !== "SUCCESS"
      ? "回答処理が通常どおり完了しませんでした。本文と状態をご確認ください。"
      : "回答を作成しました。");
    setFeedbackSaved(false);
    setFeedbackError("");
  };

  const runSubmission = async (event: FormEvent) => {
    event.preventDefault();
    if (state === "submitting" || pending?.state === "processing" || !question.trim()) return;
    const current: PendingSubmission = pending?.state === "issuing"
      ? pending
      : { key: makeIdempotencyKey(), state: "issuing" };
    savePending(current);
    setPending(current);
    setResult(null);
    setFeedbackSaved(false);
    setState("submitting");
    setMessage("送信準備をしています…");
    try {
      const registration = await api.registerKey(current.key);
      const registered: PendingSubmission = {
        ...current,
        state: "processing",
        submitBy: registration.submit_by,
        sessionExpiresAt: registration.session_expires_at,
      };
      savePending(registered);
      setPending(registered);
      setMessage("回答を作成しています…");
      applyResult(await api.createRequest(question, current.key));
      setQuestion("");
    } catch (error) {
      if (error instanceof ApiClientError && error.code === "PROCESSING") {
        const processing = { ...current, state: "processing" as const };
        savePending(processing);
        setPending(processing);
        setState("processing");
      } else {
        setState("error");
        setMessage(describeError(error));
        if (error instanceof ApiClientError && [410, 404].includes(error.status)) {
          savePending(null);
          setPending(null);
        }
      }
    }
  };

  const checkPending = async () => {
    if (!pending || state === "submitting") return;
    setState("submitting");
    setMessage("送信結果を確認しています…");
    try {
      applyResult(await api.getByKey(pending.key));
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 202) {
        setState("processing");
        setMessage("まだ回答を作成しています。時間を置いてからもう一度確認してください。");
      } else {
        setState("error");
        setMessage(describeError(error));
        if (error instanceof ApiClientError && [410, 404].includes(error.status)) {
          savePending(null);
          setPending(null);
        }
      }
    }
  };

  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault();
    if (!result || feedbackBusy) return;
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      await api.saveFeedback(result.request_id, feedback, comment);
      setFeedbackSaved(true);
    } catch (error) {
      setFeedbackError(describeError(error));
    } finally {
      setFeedbackBusy(false);
    }
  };

  return (
    <main className="page-shell">
      <header className="hero">
        <div className="brand-mark" aria-hidden="true">制</div>
        <div>
          <p className="eyebrow">MUNICIPAL POLICY GUIDE</p>
          <h1>自治体制度の問い合わせ支援</h1>
          <p className="hero-copy">人事・給与制度に関する文書を検索し、根拠を添えて回答します。</p>
        </div>
      </header>

      <aside className="demo-note" aria-label="デモについて">
        <span className="note-icon" aria-hidden="true">i</span>
        <p><strong>ポートフォリオ用デモ</strong>{" "}検索対象は架空の制度文書です。実在個人の情報や機密情報は入力しないでください。</p>
      </aside>

      <section className="panel question-panel" aria-labelledby="question-heading">
        <div className="section-heading">
          <div><p className="eyebrow">ASK A QUESTION</p><h2 id="question-heading">制度について質問する</h2></div>
          <span className="limit-badge">最大1,000文字</span>
        </div>
        <form onSubmit={runSubmission}>
          <label htmlFor="question">質問</label>
          <textarea id="question" value={question} onChange={(event) => {
            const next = event.target.value;
            if (unicodeLength(next) <= 1000) setQuestion(next);
          }}
            rows={5} placeholder="例：給与支給日はいつですか？" disabled={state === "submitting" || pending?.state === "processing"} />
          <div className="input-footer"><span>具体的な制度名や状況を含めると、根拠を探しやすくなります。</span><span aria-live="polite">{unicodeLength(question)} / 1,000</span></div>
          <button className="primary-button" type="submit" disabled={state === "submitting" || pending?.state === "processing" || !question.trim()}>
            {state === "submitting" ? <><span className="spinner" aria-hidden="true" />回答を作成中</> : <>回答を作成する <span aria-hidden="true">→</span></>}
          </button>
        </form>
        <div className={`status-line state-${state}`} role="status" aria-live="polite" aria-atomic="true">
          <span className="status-dot" aria-hidden="true" />
          <span>{message || "質問を入力して、回答を作成してください。"}</span>
        </div>
        {pending && state !== "submitting" && <div className="pending-box">
          <p>{pending.state === "issuing"
            ? "送信準備が未確定です。質問を入力して送信すると、同じ送信キーで登録を再試行します。"
            : "前回の送信結果がまだ確定していません。同じ送信キーで結果を確認します。"}</p>
          {pending.state === "processing" && <button type="button" className="secondary-button" onClick={checkPending}>送信結果を確認する</button>}
        </div>}
      </section>

      {result && <section className="result-section" aria-labelledby="result-heading">
        <div className="section-heading result-title"><div><p className="eyebrow">RESPONSE</p><h2 id="result-heading">回答</h2></div>
          <span className={`result-chip ${state === "degraded" ? "chip-warn" : "chip-ok"}`}>{result.answer_status}</span>
        </div>
        {state === "degraded" && <div className="degraded-note" role="alert"><strong>確認が必要な回答です</strong><span>通常の成功回答ではありません。状態案内と根拠をあわせてご確認ください。</span></div>}
        <article className="answer-card"><div className="answer-label">{result.answer_label || "回答内容"}</div><p className="answer-text">{result.answer || "回答本文はありません。下の案内をご確認ください。"}</p></article>

        <div className="references-heading"><div><p className="eyebrow">SOURCES</p><h3>参照した文書 <span className="count-pill">{result.references.length}</span></h3></div><p>回答の根拠を確認できます</p></div>
        {result.references.length === 0 ? <div className="empty-references">この回答に表示できる参照文書はありません。</div> : <div className="reference-list">
          {result.references.map((reference, index) => <details className="reference-card" key={reference.reference_id || `${reference.document_name}-${index}`}>
            <summary><span className="reference-index">{String(index + 1).padStart(2, "0")}</span><span className="reference-summary"><strong>{reference.document_name || "不明な文書"}</strong><span>{reference.heading}</span></span><span className="chevron" aria-hidden="true">⌄</span></summary>
            <div className="reference-body">
              <dl className="reference-meta">
                {reference.version && <div><dt>文書版</dt><dd>{reference.version}</dd></div>}
                {reference.effective_date && <div><dt>施行日</dt><dd>{reference.effective_date}</dd></div>}
                {reference.document_role && <div><dt>文書の役割</dt><dd>{reference.document_role}</dd></div>}
                {reference.page_number && <div><dt>ページ</dt><dd>{reference.page_number}ページ</dd></div>}
              </dl>
              <h4>根拠本文</h4><blockquote>{reference.content}</blockquote>
              {reference.visual_asset && !imageFailures.includes(reference.reference_id) && <figure className="reference-image">
                <img src={reference.visual_asset.url} alt={reference.visual_asset.alt} loading="lazy" onError={() => setImageFailures((ids) => [...ids, reference.reference_id])} />
                <figcaption>{reference.visual_asset.alt} · {reference.visual_asset.page_number}ページ</figcaption>
              </figure>}
              {reference.visual_asset && imageFailures.includes(reference.reference_id) && <p className="image-fallback" role="status">図表画像を読み込めませんでした。根拠本文をご確認ください。</p>}
            </div>
          </details>)}
        </div>}

        <section className="feedback-card" aria-labelledby="feedback-heading">
          <div><p className="eyebrow">YOUR FEEDBACK</p><h3 id="feedback-heading">回答へのフィードバック</h3><p>この回答への評価を保存できます。再送すると、評価内容が更新されます。</p></div>
          <form onSubmit={submitFeedback}>
            <fieldset><legend>この回答を採用しましたか？</legend><div className="feedback-options">{FEEDBACK_VALUES.map((value) => <label className={`feedback-option ${feedback === value ? "selected" : ""}`} key={value}><input type="radio" name="feedback" value={value} checked={feedback === value} onChange={() => { setFeedback(value); setFeedbackSaved(false); }} />{value}</label>)}</div></fieldset>
            <label htmlFor="feedback-comment">コメント <span className="optional">任意</span></label>
            <textarea id="feedback-comment" value={comment} rows={3} placeholder="回答の役立ち度や修正点をお聞かせください。" onChange={(event) => {
              const next = event.target.value;
              if (feedbackLength(next) <= 2000) setComment(next);
              setFeedbackSaved(false);
            }} />
            <div className="input-footer"><span>最大2,000文字（正規化後）</span><span>{feedbackLength(comment)} / 2,000</span></div>
            {feedbackError && <p className="form-error" role="alert">{feedbackError}</p>}
            {feedbackSaved && <p className="saved-message" role="status">✓ フィードバックを保存しました。</p>}
            <button type="submit" className="secondary-button" disabled={feedbackBusy}>{feedbackBusy ? "保存中…" : feedbackSaved ? "評価を更新する" : "フィードバックを保存する"}</button>
          </form>
        </section>
      </section>}

      <footer><span>自治体制度の問い合わせ支援</span><span>回答は参照文書とあわせてご確認ください。</span></footer>
    </main>
  );
}

export { App };
