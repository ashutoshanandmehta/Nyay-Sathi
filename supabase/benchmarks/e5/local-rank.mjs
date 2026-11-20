import { PGlite } from '../../../frontend/node_modules/@electric-sql/pglite/dist/index.js'
import { readFileSync, readdirSync } from 'node:fs'

const wasm = JSON.parse(readFileSync(process.argv[2],'utf8'))
const db = new PGlite()
try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; create table auth.users(id uuid primary key);
  create function auth.uid() returns uuid language sql stable as $$select null::uuid$$;`)
  for (const file of readdirSync('supabase/migrations').sort()) {
    await db.exec(readFileSync('supabase/migrations/'+file,'utf8'))
  }
  await db.exec(readFileSync('data/legal_corpus/v1/seed_legal_corpus.sql','utf8'))
  const inputs = [
    ['en','bank instant phone transfer debits savings account recipient never gets it','rbi-2019-failed-tx-tat-rules'],
    ['hi','ऑनलाइन खरीदा सामान खराब पैसे वापस refund defective goods seller','ecommerce-r6-refund'],
    ['hinglish','UPI paise kat gaye nahi mile bank muavza refund failed transaction','rbi-2019-failed-tx-tat-rules'],
  ]
  const { probes } = await import('./probes.ts')
  for (const [language,query,expected] of inputs) {
    const ranks = []
    for (const vector of [probes.find(x=>x.language===language).vector, wasm[language]]) {
      const {rows} = await db.query("select passage_id,semantic_rank from public.nyay_legal_hybrid_search($1,$2,null,null,date '2026-11-20',12)",[query, vector])
      ranks.push({hybrid:rows.findIndex(r=>r.passage_id===expected)+1,
        semantic:rows.find(r=>r.passage_id===expected)?.semantic_rank ?? null})
    }
    console.log(JSON.stringify({language,expected,reference:ranks[0],wasm:ranks[1]}))
    if(!ranks.every(rank=>rank.hybrid>0 && rank.semantic!==null)) process.exitCode=1
  }
} finally {
  await db.close()
}
