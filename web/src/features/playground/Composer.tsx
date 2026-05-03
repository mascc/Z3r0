import { Button, TextArea } from "@douyinfe/semi-ui";
import { ArrowDown, AtSign, Send, Square, X } from "lucide-react";
import { KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentMentionPicker, filterAgents } from "./AgentMentionPicker";
import type { AgentInfo } from "../../shared/api/types";

type ComposerProps = {
  streaming: boolean;
  disabled?: boolean;
  agents: AgentInfo[];
  activeAgentCode: string;
  showScrollToLatest?: boolean;
  onPickAgent: (code: string) => void;
  onScrollToLatest?: () => void;
  onSend: (text: string) => void;
  onInterrupt: () => void;
};

// matches the `@token` immediately to the left of the caret (caret == end of text)
const MENTION_REGEX = /(?:^|\s)@([\w-]*)$/;

export function Composer({
  streaming,
  disabled = false,
  agents,
  activeAgentCode,
  showScrollToLatest = false,
  onPickAgent,
  onScrollToLatest,
  onSend,
  onInterrupt,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState<{ start: number; filter: string } | null>(null);
  const [highlight, setHighlight] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);

  const wrapperRef = useRef<HTMLDivElement>(null);

  const activeAgent = useMemo(
    () => agents.find((agent) => agent.code === activeAgentCode) ?? null,
    [agents, activeAgentCode],
  );

  const candidates = useMemo(
    () => filterAgents(agents, mention?.filter ?? ""),
    [agents, mention],
  );

  const showPicker = pickerOpen || mention !== null;

  useEffect(() => {
    if (!showPicker) return;
    if (highlight >= candidates.length) {
      setHighlight(Math.max(0, candidates.length - 1));
    }
  }, [candidates, highlight, showPicker]);

  const closePicker = useCallback(() => {
    setMention(null);
    setPickerOpen(false);
    setHighlight(0);
  }, []);

  // close picker when the user clicks anywhere outside the composer wrapper
  useEffect(() => {
    if (!showPicker) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && wrapperRef.current?.contains(target)) return;
      closePicker();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [closePicker, showPicker]);

  const focusTextarea = useCallback(() => {
    wrapperRef.current?.querySelector("textarea")?.focus();
  }, []);

  const handleChange = (value: string) => {
    setText(value);
    const match = value.match(MENTION_REGEX);
    if (!match) {
      if (mention) closePicker();
      return;
    }
    setMention({ start: match.index! + match[0].indexOf("@"), filter: match[1] });
    setHighlight(0);
  };

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming || disabled) return;
    onSend(trimmed);
    setText("");
    closePicker();
  };

  const pickAgent = (agent: AgentInfo) => {
    onPickAgent(agent.code);
    if (mention) {
      const before = text.slice(0, mention.start).trimEnd();
      const after = text.slice(mention.start + 1 + mention.filter.length).trimStart();
      setText(before && after ? `${before} ${after}` : `${before}${after}`);
    }
    closePicker();
    focusTextarea();
  };

  const toggleChip = () => {
    setPickerOpen((next) => !next);
    focusTextarea();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showPicker && candidates.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlight((index) => (index + 1) % candidates.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setHighlight((index) => (index - 1 + candidates.length) % candidates.length);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        pickAgent(candidates[highlight]);
        return;
      }
      // Tab confirms the highlighted candidate (Slack-style); when only one
      // candidate is left this gives the user a one-key shortcut
      if (event.key === "Tab") {
        event.preventDefault();
        pickAgent(candidates[highlight]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closePicker();
        return;
      }
    }

    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    if (streaming) {
      onInterrupt();
    } else {
      submit();
    }
  };

  const action = streaming
    ? { icon: <Square size={16} />, type: "danger" as const, label: "Stop", onClick: onInterrupt, disabled: false }
    : { icon: <Send size={16} />, type: "primary" as const, label: "Send", onClick: submit, disabled: disabled || !text.trim() };

  return (
    <div ref={wrapperRef} className={`composer${streaming ? " composer-streaming" : ""}`}>
      <div className="composer-input">
        {showPicker ? (
          <div className="composer-picker">
            <AgentMentionPicker
              agents={candidates}
              filter={mention?.filter ?? ""}
              highlightedIndex={highlight}
              onHover={setHighlight}
              onSelect={pickAgent}
            />
          </div>
        ) : null}
        <div className="composer-row">
          <button
            type="button"
            className="composer-agent-chip"
            onClick={toggleChip}
            aria-label={activeAgent ? `Speaking to ${activeAgent.name}` : "Pick an agent"}
            title={activeAgent ? "Click to switch (or type @ in the message)" : "Pick an agent"}
          >
            <AtSign size={14} />
            <span>{activeAgent?.name || "Agent"}</span>
          </button>
          <TextArea
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            autosize={{ minRows: 1, maxRows: 8 }}
            disabled={disabled && !streaming}
            placeholder={
              disabled
                ? "Loading conversation history…"
                : streaming
                  ? "Streaming response… press Enter or stop to interrupt"
                  : "Send a message — type @ to switch agent · Shift+Enter for newline"
            }
          />
          <Button
            icon={action.icon}
            theme="solid"
            type={action.type}
            onClick={action.onClick}
            disabled={action.disabled}
            aria-label={streaming ? "Interrupt streaming" : "Send message"}
          >
            {action.label}
          </Button>
          {showScrollToLatest ? (
            <Button
              className="composer-scroll-tail"
              icon={<ArrowDown size={16} />}
              theme="solid"
              type="tertiary"
              onClick={onScrollToLatest}
              aria-label="Scroll to latest message"
            />
          ) : null}
          {showPicker ? (
            <Button
              icon={<X size={14} />}
              theme="borderless"
              type="tertiary"
              onClick={closePicker}
              aria-label="Close agent picker"
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
