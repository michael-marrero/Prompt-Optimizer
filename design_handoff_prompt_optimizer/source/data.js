// Sample data for the prototype. Real OpenRouter model identifiers.

const MODELS = [
  { id: 'anthropic/claude-sonnet-4.5', label: 'Claude Sonnet 4.5', short: 'Sonnet 4.5', vendor: 'Anthropic', tag: 'reasoning' },
  { id: 'openai/gpt-4o',               label: 'GPT-4o',            short: 'GPT-4o',     vendor: 'OpenAI',    tag: 'multimodal' },
  { id: 'google/gemini-2.0-flash',     label: 'Gemini 2.0 Flash',  short: 'Gemini 2.0', vendor: 'Google',    tag: 'fast' },
  { id: 'meta-llama/llama-3.3-70b',    label: 'Llama 3.3 70B',     short: 'Llama 3.3',  vendor: 'Meta',      tag: 'open' },
  { id: 'deepseek/deepseek-v3',        label: 'DeepSeek V3',       short: 'DeepSeek V3',vendor: 'DeepSeek',  tag: 'code'  },
  { id: 'mistralai/mistral-large',     label: 'Mistral Large',     short: 'Mistral L',  vendor: 'Mistral',   tag: 'balanced' },
];

const HISTORY = [
  { group: 'Today', items: [
    { id: 'c1', title: 'Onboarding email rewrite', when: '2m' },
    { id: 'c2', title: 'SQL: window functions for cohort retention', when: '1h' },
    { id: 'c3', title: 'Translate landing page · ja-JP', when: '3h' },
  ]},
  { group: 'Yesterday', items: [
    { id: 'c4', title: 'Refactor auth middleware (Express → Hono)', when: '1d' },
    { id: 'c5', title: 'Pricing page tier comparison', when: '1d' },
    { id: 'c6', title: 'Image prompts for hero illustration', when: '1d' },
  ]},
  { group: 'Last 7 days', items: [
    { id: 'c7', title: 'Debugging a Python traceback', when: '3d' },
    { id: 'c8', title: 'Investor update — Q2 narrative', when: '4d' },
    { id: 'c9', title: 'Customer interview synthesis', when: '6d' },
  ]},
];

const SUGGESTIONS = [
  { kind: 'Write',    text: 'Draft a follow-up email to a customer who churned' },
  { kind: 'Code',     text: 'Refactor this Python function for readability' },
  { kind: 'Analyze',  text: 'Find the top 3 themes in these support tickets' },
  { kind: 'Plan',     text: 'Outline a 6-week launch plan for a beta product' },
];

const THREAD = [
  {
    id: 'm1',
    role: 'user',
    text: 'Rewrite our onboarding email to be warmer and half as long. Keep the CTA "Set up your workspace".',
    when: '11:42 AM',
    attachments: [
      { name: 'onboarding-v3.md', size: '2.1 KB' }
    ],
  },
  {
    id: 'm2',
    role: 'assistant',
    routedTo: 'anthropic/claude-sonnet-4.5',
    routedReason: 'long-form writing · tone',
    when: '11:42 AM',
    latencyMs: 1840,
    cost: 0.0042,
    text: `Here's a tighter, warmer version — about 45% shorter:

**Subject:** Welcome to Hearth — let's get you set up

Hey {{firstName}},

Glad you're here. Hearth is built for small teams who'd rather ship than configure, so we kept setup short: pick a workspace name, invite a teammate, and you're done.

If anything feels off, just hit reply — a real person (usually me) reads every message.

**[ Set up your workspace ]**

— Maya, Hearth`,
  },
  {
    id: 'm3',
    role: 'user',
    text: 'Make the tone a touch more confident, less apologetic. And drop the signature.',
    when: '11:45 AM',
  },
  {
    id: 'm4',
    role: 'assistant',
    routedTo: 'anthropic/claude-sonnet-4.5',
    routedReason: 'iterative edit · same context',
    when: '11:45 AM',
    latencyMs: 1320,
    cost: 0.0028,
    text: `**Subject:** Welcome to Hearth — let's get you set up

Hey {{firstName}},

You're in. Hearth is for small teams who'd rather ship than configure — so setup is three steps: name your workspace, invite a teammate, start working.

Questions show up in your inbox; a real person answers within a few hours.

**[ Set up your workspace ]**`,
  },
];

window.PO_DATA = { MODELS, HISTORY, SUGGESTIONS, THREAD };
