import { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import { Bot, Send, ThumbsUp, ThumbsDown, Loader2, Sparkles, X } from 'lucide-react';

export default function AIWidget() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [feedbackSent, setFeedbackSent] = useState(false);
  const inputRef = useRef(null);

  const exampleQuestions = [
    'What are common payment issues?',
    'What are the most frequent ticket subjects?',
    'How are billing tickets usually resolved?',
    'What high-priority issues occurred recently?',
  ];

  const handleSubmit = async (e, q = null) => {
    if (e) e.preventDefault();
    const query = (q || question).trim();
    if (!query) return;
    setLoading(true);
    setError('');
    setResult(null);
    setFeedbackSent(false);
    try {
      const data = await api.aiQuery({ question: query, top_k: 5 });
      setResult(data);
      setQuestion('');
    } catch (err) {
      setError(err.message || 'AI query failed. Please try again.');
    }
    setLoading(false);
  };

  const handleFeedback = async (helpful) => {
    if (!result?.log_id) return;
    try {
      await api.aiFeedback({ log_id: result.log_id, helpful });
      setFeedbackSent(true);
    } catch {}
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={18} className="text-indigo-500" />
          <h3 className="text-sm font-semibold">Ask AI</h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Ask questions about your support tickets and get AI-powered insights.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Example questions */}
        {!result && !loading && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
              Try asking…
            </p>
            <div className="flex flex-wrap gap-2">
              {exampleQuestions.map((q) => (
                <button
                  key={q}
                  onClick={(e) => handleSubmit(e, q)}
                  className="px-3 py-1.5 text-xs bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 rounded-full hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center gap-3 text-gray-500 text-sm">
            <Loader2 size={18} className="animate-spin text-indigo-500" />
            <span>Searching tickets and generating answer…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            {/* Answer */}
            <div className="p-4 rounded-xl bg-indigo-50 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-800">
              <div className="flex items-center gap-2 mb-2">
                <Bot size={16} className="text-indigo-600 dark:text-indigo-400" />
                <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wide">
                  AI Answer
                </span>
                <span className="ml-auto text-xs text-gray-400">
                  {result.latency_ms}ms · {result.tokens_used} tokens
                </span>
              </div>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.answer}</p>
            </div>

            {/* Citations */}
            {result.citations && result.citations.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                  Referenced Tickets ({result.retrieved_count})
                </p>
                <div className="space-y-1.5">
                  {result.citations.map((c) => (
                    <div
                      key={c.ticket_id}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs"
                    >
                      <div>
                        <span className="font-medium text-indigo-600 dark:text-indigo-400">{c.ticket_number}</span>
                        <span className="mx-2 text-gray-400">·</span>
                        <span className="text-gray-600 dark:text-gray-300">{c.subject}</span>
                      </div>
                      <span className="text-gray-400 tabular-nums">
                        {(c.relevance_score * 100).toFixed(0)}% match
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Feedback */}
            <div className="flex items-center gap-3 pt-1">
              <span className="text-xs text-gray-400">Was this helpful?</span>
              {feedbackSent ? (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Thanks for your feedback!</span>
              ) : (
                <>
                  <button
                    onClick={() => handleFeedback(true)}
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg hover:bg-emerald-50 dark:hover:bg-emerald-950/20 text-gray-500 hover:text-emerald-600 transition"
                  >
                    <ThumbsUp size={13} /> Yes
                  </button>
                  <button
                    onClick={() => handleFeedback(false)}
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/20 text-gray-500 hover:text-red-600 transition"
                  >
                    <ThumbsDown size={13} /> No
                  </button>
                </>
              )}
              <button
                onClick={() => { setResult(null); setError(''); setFeedbackSent(false); }}
                className="ml-auto text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1 transition"
              >
                <X size={12} /> Clear
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-800 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about your tickets…"
            disabled={loading}
            className="flex-1 px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="p-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition disabled:opacity-50"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </form>
      </div>
    </div>
  );
}
