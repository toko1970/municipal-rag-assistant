import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

const result = {
  request_id: "0b8d9b13-4274-4b79-9965-5b9fedc07852",
  answer: "給与支給日は毎月21日です。",
  answer_label: "制度に基づく回答",
  answer_status: "SUCCESS",
  degraded: false,
  references: [{
    reference_id: "a340e87b-dd5b-4b4e-b6c2-3ef736ace4aa",
    document_name: "給与規則",
    version: "2025年度版",
    effective_date: "2025-04-01",
    document_role: "規則",
    heading: "支給日",
    page_number: 12,
    content: "給料は毎月21日に支給する。",
    visual_asset: { url: "/api/requests/0b8d9b13-4274-4b79-9965-5b9fedc07852/references/a340e87b-dd5b-4b4e-b6c2-3ef736ace4aa/image", mime_type: "image/png" as const, page_number: 12, alt: "給与規則 p.12の図表" },
  }],
  generation: {},
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => cleanup());

describe("public UI contract", () => {
  it("stores a browser key before registering, calls the RAG API once, and renders expandable citations", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockImplementationOnce(async () => {
      expect(sessionStorage.getItem("rag-demo-pending-submission-v1")).not.toBeNull();
      return jsonResponse({ submit_by: "2026-11-03T01:05:00Z", session_expires_at: "2026-11-04T00:00:00Z" });
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(result));
    render(<App />);
    await user.type(screen.getByRole("textbox", { name: "質問" }), "給与支給日はいつですか？");
    await user.click(screen.getByRole("button", { name: /回答を作成する/ }));
    await screen.findByText("給与支給日は毎月21日です。");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const firstKey = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    const secondKey = fetchMock.mock.calls[1][1]?.headers as Record<string, string>;
    expect(firstKey["Idempotency-Key"]).toMatch(/^[A-Za-z0-9_-]{43,}$/);
    expect(secondKey["Idempotency-Key"]).toBe(firstKey["Idempotency-Key"]);
    expect(sessionStorage.length).toBe(0);
    await user.click(screen.getByText("給与規則"));
    expect(screen.getByText("給料は毎月21日に支給する。")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "給与規則 p.12の図表" })).toHaveAttribute("src", result.references[0].visual_asset.url);
    cleanup();
    render(<App />);
    expect(screen.queryByText("給与支給日は毎月21日です。")).not.toBeInTheDocument();
  });

  it("keeps a pending key for manual result lookup after reload and removes it after success", async () => {
    sessionStorage.setItem("rag-demo-pending-submission-v1", JSON.stringify({ key: "a".repeat(43), state: "processing" }));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(result));
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("前回の送信結果を確認できます。自動で再送はしません。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "送信結果を確認する" }));
    await screen.findByText("給与支給日は毎月21日です。");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/requests/by-idempotency-key");
    expect(sessionStorage.length).toBe(0);
  });

  it("blocks a new question while an earlier key is still unresolved", () => {
    sessionStorage.setItem("rag-demo-pending-submission-v1", JSON.stringify({ key: "a".repeat(43), state: "processing" }));
    render(<App />);

    expect(screen.getByRole("textbox", { name: "質問" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /回答を作成する/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "送信結果を確認する" })).toBeEnabled();
  });

  it("does not label degraded or non-success answers as normal success", async () => {
    const degradedResult = { ...result, answer_status: "PARTIAL", degraded: true };
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(jsonResponse({ submit_by: "2026-11-03T01:05:00Z", session_expires_at: "2026-11-04T00:00:00Z" }));
    fetchMock.mockResolvedValueOnce(jsonResponse(degradedResult));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByRole("textbox", { name: "質問" }), "質問");
    await user.click(screen.getByRole("button", { name: /回答を作成する/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("確認が必要な回答です");
    expect(screen.getByText("PARTIAL")).toBeInTheDocument();
  });

  it("saves feedback by request ID and announces the saved or updated state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(jsonResponse({ submit_by: "2026-11-03T01:05:00Z", session_expires_at: "2026-11-04T00:00:00Z" }));
    fetchMock.mockResolvedValueOnce(jsonResponse(result));
    fetchMock.mockResolvedValueOnce(jsonResponse({ saved: true }));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByRole("textbox", { name: "質問" }), "質問");
    await user.click(screen.getByRole("button", { name: /回答を作成する/ }));
    await screen.findByText("給与支給日は毎月21日です。");
    await user.click(screen.getByLabelText("修正して採用した"));
    await user.type(screen.getByRole("textbox", { name: /コメント/ }), "説明を補足しました。");
    await user.click(screen.getByRole("button", { name: "フィードバックを保存する" }));
    expect(await screen.findByText("✓ フィードバックを保存しました。")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toContain(`${result.request_id}/feedback`);
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({ value: "修正して採用した", comment: "説明を補足しました。" });
  });

  it("retries a lost key-registration response with the same sessionStorage key", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    fetchMock.mockResolvedValueOnce(jsonResponse({ submit_by: "2026-11-03T01:05:00Z", session_expires_at: "2026-11-04T00:00:00Z" }));
    fetchMock.mockResolvedValueOnce(jsonResponse(result));
    render(<App />);
    await user.type(screen.getByRole("textbox", { name: "質問" }), "給与支給日はいつですか？");
    await user.click(screen.getByRole("button", { name: /回答を作成する/ }));
    expect(await screen.findByText("通信に失敗しました。接続を確認してください。")).toBeInTheDocument();
    const saved = JSON.parse(sessionStorage.getItem("rag-demo-pending-submission-v1")!);
    await user.click(screen.getByRole("button", { name: /回答を作成する/ }));
    await screen.findByText("給与支給日は毎月21日です。");
    expect(fetchMock.mock.calls[0][1]?.headers).toEqual(fetchMock.mock.calls[1][1]?.headers);
    expect(saved.state).toBe("issuing");
  });

  it("counts question limits in Unicode code points, including emoji", () => {
    render(<App />);
    const field = screen.getByRole("textbox", { name: "質問" });
    fireEvent.change(field, { target: { value: "😀".repeat(1000) } });
    expect(screen.getByText("1000 / 1,000")).toBeInTheDocument();
    fireEvent.change(field, { target: { value: "😀".repeat(1001) } });
    expect(field).toHaveValue("😀".repeat(1000));
  });
});
