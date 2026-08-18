"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeftIcon } from "../../../../components/icons";
import { EvaluationWizard } from "../../../../components/evaluation-wizard";
import { PageHeader } from "../../../../components/page-header";
import { InlineAlert, Skeleton } from "../../../../components/ui";
import { api } from "../../../../lib/api";
import type { DatasetVersion } from "../../../../lib/types";
import { useLocale } from "../../../../lib/i18n";

export default function NewEvaluationPage() {
  const { t } = useLocale();
  const [datasets, setDatasets] = useState<DatasetVersion[]>([]); const [error, setError] = useState("");
  useEffect(() => { api<DatasetVersion[]>("/api/datasets").then(setDatasets).catch(() => setError(t("unableLoadDatasets"))); }, [t]);
  return <main className="shell"><Link href="/app/evaluations" className="back-link"><ArrowLeftIcon size={16} />{t("backToEvaluations")}</Link><PageHeader eyebrow={t("newEvaluation")} title={t("configure")} description={t("configureLead")} />{error ? <InlineAlert tone="error">{error}</InlineAlert> : datasets.length ? <EvaluationWizard datasets={datasets} /> : <div className="panel loading-list"><Skeleton /><Skeleton /><Skeleton /></div>}</main>;
}
