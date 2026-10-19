-- Statistiques de Rosace (à coller dans Supabase > SQL Editor, puis « Run »).
-- AVANT de lancer : remplace MON_MOT_DE_PASSE (tout en bas) par le mot de passe de ta page de stats.

create extension if not exists pgcrypto;

-- Une ligne par élève et par jour d'activité
create table if not exists public.activite (
  eleve text not null,
  jour date not null default current_date,
  cours text[] not null default '{}',
  xp int not null default 0,
  lues int not null default 0,
  pages int not null default 1,
  maj_le timestamptz not null default now(),
  primary key (eleve, jour)
);
alter table public.activite enable row level security; -- aucune lecture directe depuis le site

-- Le mot de passe de la page de stats (stocké chiffré, illisible depuis le site)
create table if not exists public.admin_config (id int primary key default 1, mdp text not null);
alter table public.admin_config enable row level security;

-- Appelée par le site à chaque page vue
create or replace function public.noter_visite(p_eleve text, p_cours text[], p_xp int, p_lues int)
returns void language sql security definer set search_path = public as $$
  insert into activite (eleve, cours, xp, lues) values (left(p_eleve, 64), p_cours[1:5], p_xp, p_lues)
  on conflict (eleve, jour) do update
    set cours = excluded.cours, xp = excluded.xp, lues = excluded.lues, pages = activite.pages + 1, maj_le = now();
$$;
grant execute on function public.noter_visite(text, text[], int, int) to anon;

-- Lue uniquement par la page de stats, avec le mot de passe
create or replace function public.stats_admin(p_mdp text)
returns json language plpgsql security definer set search_path = public, extensions as $$
declare r json;
begin
  if not exists (select 1 from admin_config where id = 1 and mdp = crypt(p_mdp, mdp)) then
    raise exception 'mot de passe incorrect';
  end if;
  with dern as (select distinct on (eleve) eleve, cours, xp, lues from activite order by eleve, jour desc),
       prem as (select eleve, min(jour) as j from activite group by eleve)
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
               (select count(*) from prem p where p.j = d::date) as nouveaux
        from generate_series(current_date - 29, current_date, interval '1 day') d) x),
    'par_cours', (select coalesce(json_object_agg(c, n), '{}') from (select unnest(cours) as c, count(*) as n from dern group by 1) y)
  ) into r;
  return r;
end $$;
grant execute on function public.stats_admin(text) to anon;

insert into admin_config (id, mdp) values (1, crypt('MON_MOT_DE_PASSE', gen_salt('bf')))
on conflict (id) do update set mdp = excluded.mdp;
