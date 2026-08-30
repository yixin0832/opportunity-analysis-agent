"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, ClipboardCheck, Milestone } from "lucide-react";
import { analyze, getExamples } from "@/lib/api";
import type { ExampleInput } from "@/lib/types";
import { Button, Card, SectionTitle, Textarea } from "@/components/ui";
import { ErrorBlock } from "@/components/result-view";

export default function HomePage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [examples, setExamples] = useState<ExampleInput[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const example = examples[0];

  useEffect(() => {
    getExamples().then(setExamples).catch(() => setExamples([]));
  }, []);

  async function handleAnalyze() {
    if (!input.trim()) {
      setError("请先输入销售拜访记录。");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await analyze(input.trim());
      router.replace(`/analyses/${response.analysis_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "本次分析未能完成，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-65px)] max-w-5xl flex-col px-5 py-6 sm:py-8">
      <section className="mx-auto w-full max-w-3xl text-center">
        <h1 className="text-[30px] font-semibold leading-tight text-slate-950 sm:text-[34px]">
          商机录入与分析助手
        </h1>
        <p className="mx-auto mt-2.5 max-w-2xl text-[17px] leading-7 text-slate-700">
          自动提取 CRM 字段、判断销售阶段，并标注风险与待确认信息
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2.5 text-[13px] leading-5 text-slate-600">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 shadow-sm shadow-slate-200/50">
            <ClipboardCheck className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
            CRM 字段抽取
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 shadow-sm shadow-slate-200/50">
            <Milestone className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
            销售阶段判断
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 shadow-sm shadow-slate-200/50">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
            风险与待确认提示
          </span>
        </div>
      </section>

      <div className="mx-auto mt-5 w-full max-w-3xl">
        <Card className="p-5 shadow-sm shadow-slate-200/50 sm:p-6">
          <SectionTitle
            title="销售拜访记录"
            description="粘贴本次销售拜访记录、客户沟通纪要或会议记录，系统将按规则提取商机字段、判断销售阶段，并标注风险、冲突和待确认信息。"
          />
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="例如：今天和远川零售集团数字化负责人陈总、采购刘经理开了方案评审会。客户确认门店售后咨询和会员活动问答是今年重点改造场景，已经试用过我们的智能客服方案，客服团队反馈效果可以继续推进。陈总表示今年预算约 80 万，采购刘经理询问了正式报价、付款方式和采购流程，项目需要进入内部立项审批，并计划本月底完成供应商选择。最终由陈总负责审批。客户确认下一步行动是由销售负责人张晨在本周五前发送正式报价和实施计划给采购刘经理。"
            className="min-h-[200px] text-[15px] leading-7"
          />
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {example ? (
              <Button variant="ghost" onClick={() => setInput(example.input_text)} disabled={loading} className="h-11 justify-start px-0 text-slate-500 hover:bg-transparent hover:text-slate-950">
                使用示例记录
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={handleAnalyze} disabled={loading} size="lg" className="gap-2 px-7 sm:min-w-36">
              {loading ? "正在分析..." : "开始分析"}
              {!loading ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
            </Button>
          </div>
        </Card>
        {error ? <div className="mt-4"><ErrorBlock message={error} /></div> : null}
      </div>
    </div>
  );
}
