-- Rosace : suivi des élèves dans la page Stats.
-- À coller dans Supabase > SQL Editor, puis « Run ». Rien à modifier.

alter table public.activite add column if not exists detail jsonb not null default '{}';
alter table public.activite add column if not exists email text;

drop function if exists public.noter_visite(text, text[], int, int);
create or replace function public.noter_visite(p_eleve text, p_cours text[], p_xp int, p_lues int,
  p_detail jsonb default '{}', p_email text default null)
returns void language sql security definer set search_path = public as $$
  insert into activite (eleve, cours, xp, lues, detail, email)
  values (left(p_eleve, 64), p_cours[1:5], p_xp, p_lues, coalesce(p_detail, '{}'), left(p_email, 120))
  on conflict (eleve, jour) do update
    set cours = excluded.cours, xp = excluded.xp, lues = excluded.lues, detail = excluded.detail,
        email = coalesce(excluded.email, activite.email), pages = activite.pages + 1, maj_le = now();
$$;
grant execute on function public.noter_visite(text, text[], int, int, jsonb, text) to anon;

create or replace function public.stats_admin(p_mdp text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare r json;
begin
  if not exists (select 1 from admin_config where id = 1 and mdp = crypt(p_mdp, mdp)) then
    raise exception 'mot de passe incorrect';
  end if;
  with dern as (select distinct on (eleve) eleve, cours, xp, lues, detail, maj_le from activite order by eleve, jour desc),
       prem as (select eleve, min(jour) as j, count(*) as nb from activite group by eleve),
       noms as (select a.eleve, coalesce(max(a.email), max(u.email::text)) as email
                from activite a left join auth.users u on u.id::text = a.eleve group by a.eleve)
  select json_build_object(
    'eleves', (select count(*) from prem),
    'aujourdhui', (select count(*) from activite where jour = current_date),
    'semaine', (select count(distinct eleve) from activite where jour > current_date - 7),
    'mois', (select count(distinct eleve) from activite where jour > current_date - 30),
    'pages_semaine', (select coalesce(sum(pages), 0) from activite where jour > current_date - 7),
    'lecons_lues', (select coalesce(sum(lues), 0) from dern),
    'xp_moyen', (select coalesce(round(avg(xp)), 0) from dern),
    'revenus_j7', (select count(*) from (select eleve from activite where jour > current_date - 7 group by eleve having count(*) >= 2) x),
    'par_jour', (select coalesce(json_agg(x order by x.jour), '[]') from (
        select d::date as jour,
               (select count(*) from activite a where a.jour = d::date) as actifs,
               (select count(*) from prem p where p.j = d::date) as nouveaux,
               (select coalesce(json_agg(coalesce(n.email, 'Élève sans compte')), '[]') from activite a join noms n using (eleve) where a.jour = d::date) as qui
        from generate_series(current_date - 29, current_date, interval '1 day') d) x),
    'par_cours', (select coalesce(json_object_agg(c, n), '{}') from (select unnest(cours) as c, count(*) as n from dern group by 1) y),
    'liste', (select coalesce(json_agg(e order by e.derniere desc), '[]') from (
        select coalesce(n.email, 'Élève sans compte') as nom, p.j as premier, d.maj_le as derniere, p.nb as jours,
               d.xp, d.lues, d.detail
        from dern d join prem p using (eleve) join noms n using (eleve)) e)
  ) into r;
  return r;
end $$;
grant execute on function public.stats_admin(text) to anon;
