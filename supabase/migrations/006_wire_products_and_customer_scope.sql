alter table customer_profiles
  add column if not exists wire_product text not null default 'finance';

alter table wire_candidates
  add column if not exists customer_profile_id bigint references customer_profiles(id) on delete cascade;

update wire_candidates
set customer_profile_id = (
  select cp.id
  from customer_profiles cp
  order by cp.auto_post_enabled desc, cp.id asc
  limit 1
)
where customer_profile_id is null;

alter table wire_candidates
  drop constraint if exists wire_candidates_external_id_key;

create unique index if not exists uq_wire_candidates_customer_external
  on wire_candidates(customer_profile_id, external_id);

create index if not exists idx_wire_candidates_customer_profile_id
  on wire_candidates(customer_profile_id);

create index if not exists idx_wire_candidates_customer_source_created
  on wire_candidates(customer_profile_id, source_name, created_at);
