-- AXORA: compromissos com fim definido gerados por completo.
-- Recorrências indeterminadas permanecem com janela móvel de 18 meses.
-- Não altera vencimentos existentes, pagos, cancelados nem revisões.
BEGIN;

CREATE OR REPLACE FUNCTION public.axora_ensure_provisions(
  p_workspace_id uuid,p_through date DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_added integer; v_until date:=coalesce(p_through,(current_date+interval '18 months')::date);
BEGIN
  IF v_until>current_date+interval '30 months' THEN
    RAISE EXCEPTION 'Janela de geração excede 30 meses';
  END IF;
  WITH series AS (
    SELECT r.id,r.workspace_id,gs.seq,r.recurrence,r.end_date,r.installment_count,
      coalesce(rev.description,r.description) description,
      coalesce(rev.category,r.category) category,
      coalesce(rev.responsible,r.responsible) responsible,
      coalesce(rev.value_mode,r.value_mode) value_mode,
      coalesce(rev.planned_value,r.planned_value) amount,
      public.axora_due_at(coalesce(rev.anchor_due_date,r.start_due_date),r.frequency,
                          gs.seq-coalesce(rev.effective_sequence,1)) due_date
    FROM public.finance_provision_rules r
    CROSS JOIN LATERAL generate_series(
      1,
      CASE
        WHEN r.recurrence='once' THEN 1
        WHEN r.recurrence IN ('installments','until_date') AND r.installment_count IS NOT NULL
          THEN least(360,r.installment_count)
        WHEN r.recurrence='until_date' AND r.end_date IS NOT NULL
          THEN least(5000,greatest(1,ceil((r.end_date-r.start_due_date)::numeric/7)::integer+3))
        ELSE least(5000,greatest(1,ceil((v_until-r.start_due_date)::numeric/7)::integer+3))
      END
    ) AS gs(seq)
    LEFT JOIN LATERAL (
      SELECT v.* FROM public.finance_provision_revisions v
      WHERE v.rule_id=r.id AND v.workspace_id=r.workspace_id
        AND v.effective_sequence<=gs.seq
      ORDER BY v.effective_sequence DESC LIMIT 1
    ) rev ON true
    WHERE r.active AND r.workspace_id=p_workspace_id
      AND (r.stop_before_sequence IS NULL OR gs.seq<r.stop_before_sequence)
  )
  INSERT INTO public.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,
    description_override,category_override,responsible_override,value_mode_override
  )
  SELECT s.id,s.workspace_id,s.seq,s.due_date,s.amount,
         -- Snapshot por ocorrência: futuras alterações não mudam pagamentos anteriores.
         s.description,s.category,s.responsible,s.value_mode
  FROM series s
  WHERE (s.recurrence IN ('once','installments','until_date') OR s.due_date<=v_until)
    AND (s.recurrence<>'once' OR s.seq=1)
    AND (s.recurrence<>'until_date' OR
         ((s.installment_count IS NOT NULL AND s.seq<=s.installment_count) OR
          (s.installment_count IS NULL AND s.due_date<=s.end_date)))
    AND (s.recurrence<>'installments' OR s.seq<=s.installment_count)
  ON CONFLICT(rule_id,sequence_no) DO NOTHING;
  GET DIAGNOSTICS v_added=ROW_COUNT;
  RETURN v_added;
END;
$$;



-- Soma diretamente no PostgreSQL para evitar cortes do limite de linhas
-- da API REST do Supabase; inclui todas as parcelas em aberto.
CREATE OR REPLACE FUNCTION public.axora_provision_overview(p_workspace_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
  WITH due AS (
    SELECT i.due_date,i.planned_value,
           coalesce(i.description_override,r.description) description,
           i.id
    FROM public.finance_provision_occurrences i
    JOIN public.finance_provision_rules r
      ON r.id=i.rule_id AND r.workspace_id=i.workspace_id
    WHERE i.workspace_id=p_workspace_id AND i.status='open'
  ),
  upcoming AS (
    SELECT due_date,description,planned_value,id
    FROM due ORDER BY due_date,id LIMIT 5
  )
  SELECT jsonb_build_object(
    'to_pay',(SELECT coalesce(sum(planned_value),0) FROM due),
    'pending_count',(SELECT count(*) FROM due),
    'next_forecasts',coalesce((
       SELECT jsonb_agg(jsonb_build_object(
          'due_date',due_date,'description',description,'type','Saída',
          'status','Não pago','final_value',planned_value) ORDER BY due_date,id)
       FROM upcoming
    ),'[]'::jsonb)
  );
$$;
REVOKE ALL ON FUNCTION public.axora_provision_overview(uuid)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_provision_overview(uuid) TO service_role;
COMMIT;
NOTIFY pgrst,'reload schema';
