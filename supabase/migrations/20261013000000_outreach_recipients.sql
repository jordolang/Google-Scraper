-- Everyone the app has emailed, with the token in their Unsubscribe link and
-- when (if ever) they used it. The desktop app writes rows with the project's
-- secret key; the unsubscribe Edge Function marks them. Nothing else can read
-- the table: RLS is on and there are no policies, so the public anon and
-- publishable keys see nothing.
create table if not exists public.outreach_recipients (
  email text primary key check (email = lower(email)),
  token text not null unique,
  created_at timestamptz not null default now(),
  unsubscribed_at timestamptz,
  -- 'one-click' (the inbox's own Unsubscribe button) or 'link' (the footer).
  unsubscribe_method text
);

alter table public.outreach_recipients enable row level security;
revoke all on public.outreach_recipients from anon, authenticated;

create index if not exists outreach_recipients_unsubscribed_idx
  on public.outreach_recipients (unsubscribed_at)
  where unsubscribed_at is not null;
