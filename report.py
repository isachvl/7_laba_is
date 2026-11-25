import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from gate import read

def trim(v,n=240):
    v=' '.join(str(v).split());return v if len(v)<=n else v[:n]+'...'
def ids(v):return ', '.join(i.removeprefix('user_task_') for i in v) or 'нет'
def main():
    s=read('analysis/summary.json');reviews=read('analysis/reviews.json');config=read('config.json');frozen=read('frozen.json')
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'));pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
    body=ParagraphStyle('body',fontName='Arial',fontSize=8.7,leading=11,spaceAfter=5)
    small=ParagraphStyle('small',parent=body,fontSize=7.3,leading=9,spaceAfter=4)
    heading=ParagraphStyle('heading',parent=body,fontName='ArialBold',fontSize=11.5,leading=14,spaceBefore=6,spaceAfter=5)
    title=ParagraphStyle('title',parent=heading,fontSize=18,leading=22,spaceAfter=9)
    story=[]
    def p(v,style=body):story.append(Paragraph(escape(str(v)),style))
    def table(data,widths):
        t=Table([[Paragraph(escape(str(c)),small) for c in row] for row in data],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e3edf8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.25,HexColor('#cbd5df')),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]));story.extend([t,Spacer(1,5)])
    p('ЛР7. Наблюдаемость и регрессия',title)
    p('ReAct ЛР4, AgentDojo 0.1.35 / workspace v1.2.2, Qwen3-4B-Instruct-2507 Q4_K_M, llama.cpp b12110, MLflow 3.18.0. T=0, seed=42, контекст 16384, ответ до 1024 токенов, до 15 вызовов модели и 15 попыток инструментов. Основная оценка: 30 задач x 3 повтора x 4 серии = 360 эпизодов; дополнительно 20 парных эпизодов на отладочных задачах.')
    p('1. Версия, трейс и правило принятия',heading)
    p('Манифест содержит коммит '+frozen['commit'][:8]+', SHA-256 кода, промптов, конфигурации и описаний 24 инструментов, ревизию и SHA-256 весов, квантование, сервер, параметры и версию стенда. A/A использует тот же манифест, что база. Часы создания объектов внутри симулятора фиксированы; реальные таймеры MLflow не изменялись.',small)
    p('Трейс: корень AGENT, дочерние CHAT_MODEL и TOOL. Записаны входы/выходы, модель, токены, имя и аргументы инструмента, полная и видимая длина результата, ошибки. Теги: задача, версия, повтор, utility и причина остановки. Первый реальный трейс считан из базы с flush и проверен: 4 спана, 2 вызова модели, 1 инструмент; порядок и токены совпали с журналом ЛР4.',small)
    table([['Статус','Условие'],['ERROR','Нет полных трёх повторов, разные задачи/стенд или некорректная сводка'],['FAIL','Не прошли тесты или защищаемая задача решена кандидатом менее 2/3 раз'],['REVIEW','Потерь нет, но защищаемых задач <5; либо потери на остальных в среднем >=1 задачи; либо медиана суммы токенов или времени выросла >25%'],['PASS','Остальные случаи']],[70,430])
    p('Защищаются только задачи с 3/3 у базы: защита единичных успехов добавила бы неустойчивые случаи и ложные потери. Улучшения других задач не компенсируют потерю защищаемой. Затраты для гейта - входные плюс выходные токены за эпизод. Правила и пороги записаны до результатов.',small)
    p('Прогноз',heading)
    p('Обрезка результата до 2000 символов может потерять данные list_files и больших документов; ожидаемые риски - задачи 26, 27, 35, статус FAIL. Вход должен уменьшиться, но возможны лишние поиски. Исправление сохраняет 2000 символов и добавляет пометку об обрезке. Для A/A ожидался PASS; строгий гейт без большинства должен давать не меньше потерь.',small)
    p('2. Цена трейсинга: 10 пар',heading)
    records=read('eval/overhead/summary.json')['records'];off={r['task']:r for r in records if r['version']=='off'};on={r['task']:r for r in records if r['version']=='on'}
    data=[['Задача','Успех off/on','Вход off/on','Выход off/on','Время off/on, с']]
    for i in off:data.append([i.removeprefix('user_task_'),f"{off[i]['utility']}/{on[i]['utility']}",f"{off[i]['input_tokens']}/{on[i]['input_tokens']}",f"{off[i]['output_tokens']}/{on[i]['output_tokens']}",f"{off[i]['seconds']:.2f}/{on[i]['seconds']:.2f}"])
    table(data,[45,90,120,115,130])
    o=s['overhead'];p(f"Вердикты совпали {o['utility_equal']}/10, токены {o['token_equal']}/10, числа вызовов {o['calls_equal']}/10. Медиана времени {o['timing']['off']['median']:.3f} -> {o['timing']['on']['median']:.3f} с. Время измерено до закрытия корневого спана; последующий flush/экспорт исключён.",small)
    p(reviews['overhead_note'],small)
    replay=read('analysis/replay_control.json');p(f"Контроль с фиксированными сохранёнными ответами, без генерации: исходы, вызовы и токены совпали 10/10; медианы времени {replay['off_median_seconds']*1000:.2f}/{replay['on_median_seconds']*1000:.2f} мс. Это измерение обвязки на replay, не времени Qwen.",small)
    story.append(PageBreak())
    p('3. База, A/A и сводки версий',title)
    data=[['Серия','Успехи по повторам /30','Всего /90','Медиана суммы вход+выход','Медиана времени, с','Гейт']]
    for n,m in s['metrics'].items():data.append([n,' / '.join(str(v) for v in m['per_run_successes']),m['successes'],f"{m['total_tokens']['median']:.0f}",f"{m['seconds']['median']:.2f}",'BASE' if n=='base' else s['gates'][n]['status']])
    table(data,[55,105,60,125,85,70])
    aa=s['gates']['aa'];p('Защищаемых задач '+str(len(aa['protected']))+' из 30: '+ids(aa['protected'])+'. A/A сравнивает две независимые серии той же системы, по три повтора. Статус '+aa['status']+'; причины: '+'; '.join(aa['reason'])+'.',small)
    p(reviews['aa_note'],small)
    story.append(Image('analysis/versions.png',width=500,height=140))
    p('Четыре сигнала наблюдения',heading)
    data=[['Показатель','base','aa','candidate','fix']]
    for label,key in [('Модель, вызовы','model_calls'),('Инструменты, вызовы','tool_calls')]:data.append([label]+[s['metrics'][n][key]['sum'] for n in ['base','aa','candidate','fix']])
    data.append(['Ошибки инструментов']+[s['metrics'][n]['tool_errors'] for n in ['base','aa','candidate','fix']]);data.append(['Остановки по лимитам']+[s['metrics'][n]['limit_stops'] for n in ['base','aa','candidate','fix']]);data.append(['Максимальный вход /16384']+[s['metrics'][n]['max_input_tokens']['max'] for n in ['base','aa','candidate','fix']])
    table(data,[160,85,85,85,85])
    p('Задержка - время эпизода; нагрузка - число вызовов; ошибки - ошибки инструментов и остановки по лимитам; насыщение - токены и заполнение контекста. Полные показатели сохранены в сводках и HTML-дашбордах.',small)
    p('Проверка без правила большинства',heading)
    strict=s['strict_aa'];table([['Гейт на A/A','Статус','Потеряны'],['Кандидат должен решить >=2/3',aa['status'],ids(aa['lost'])],['Кандидат должен решить 3/3',strict['status'],ids(strict['lost'])]],[210,70,220])
    p('Прогноз до пересчёта: строгий вариант не может уменьшить число потерь, потому что одиночная неудача уже считается регрессией. '+reviews['strict_note'],small)
    p('CI без модели',heading)
    p('GitHub Actions устанавливает requirements-ci.txt, запускает unittest и gate.py по сохранённым сводкам. Генерация выполняется отдельно на машине с моделью. FAIL/ERROR дают ненулевой код завершения; REVIEW требует ручного решения. Конфигурация: .github/workflows/regression.yml. '+reviews['ci_note'],small)
    controls=s['controls'];p('Отрицательный контроль: сценарный агент на пяти задачах, по три повтора; сломанная обвязка теряет последний результат. Защищены все пять, потеряны '+ids(controls['lost'])+', гейт '+controls['status']+'. Проверены синтетические потери с улучшением, слабая защита, пропущенный повтор, несовпадающий стенд и пороги затрат.',small)
    story.append(PageBreak())
    p('4. Изменение: первые 2000 символов',title)
    c=s['gates']['candidate'];p('Изменён только видимый модели результат успешного инструмента: первые 2000 символов. Полный исходный результат сохранён в TOOL-спане и собственном трейсе. Кандидат прогнан на тех же 30 задачах трижды. Статус '+c['status']+'. Потеряны '+ids(c['lost'])+'; новые решённые большинством '+ids(c['new'])+'.')
    p('Ниже для каждой потери выбран первый неуспешный повтор кандидата и тот же номер повтора базы. Исключены случайные ID вызовов при сравнении ответов модели. Указано именно первое различие сохранённой последовательности; первая обрезка фиксируется отдельно, чтобы не приписывать ей более раннее расхождение.',small)
    lookup={v['task']:v for v in reviews['candidate_cases']}
    for case in [v for v in s['comparisons'] if v['version']=='candidate']:
        task=case['task'];d=case['first_difference'];p(task+'; кандидат '+str(sum(case['candidate_runs']))+'/3',heading)
        if d:
            a=d['base'];b=d['candidate'];p(f"Первое различие: событие {d['event']}, тип {(b or a)['kind']}. Спаны: base={(a or {}).get('span_id')}, candidate={(b or {}).get('span_id')}.",small)
            if b and b['kind']=='tool':p('Инструмент '+b['name']+': база '+str(len((a or {}).get('output','')))+' символов, кандидат '+str(len(b.get('output','')))+' символов.',small)
            else:p('База: '+trim((a or {}).get('response',a),180)+'; кандидат: '+trim((b or {}).get('response',b),180),small)
            p('Трейсы: '+d['base_trace_id']+' / '+d['candidate_trace_id'],small)
        p(lookup[task]['explanation'],small)
    p('Почему улучшения не компенсируют потерю',heading)
    p('Вопрос защиты: одна защищаемая задача потеряна, две новые решены. Среднее может вырасти на одну задачу, но гейт выдаёт FAIL: он проверяет сохранение гарантируемого поведения, а не только среднюю успешность. Статус REVIEW относится к более мягким отклонениям при отсутствии защищаемых потерь.',small)
    p('Статус спана и успех задачи',heading)
    e=s['semantic_example'];r=e['record'];p(r['task']+', повтор '+str(r['run']+1)+', трейс '+r['trace_id']+': корень завершён OK, но utility=False. Запрос: '+trim(e['query'],160),small)
    p('Ответ: '+trim(e['answer'],300),small);p(reviews['semantic_note'],small)
    story.append(PageBreak())
    p('5. Попытка исправления и решение',title)
    f=s['gates']['fix'];p('Исправление сохраняет предел 2000 символов, включая явную пометку TRUNCATED TOOL RESULT и рекомендацию уточнить запрос. Длинный ответ заменён пометкой и началом исходного текста. Модель, промпт, задачи, T=0 и лимиты сохранены. Исправленный кандидат прогнан трижды на всех 30 задачах.')
    table([['Сравнение','Статус','Защищаемые потери','Новые задачи'],['База / A/A',aa['status'],ids(aa['lost']),ids(aa['new'])],['База / изменение',c['status'],ids(c['lost']),ids(c['new'])],['База / исправление',f['status'],ids(f['lost']),ids(f['new'])]],[115,65,160,160])
    story.append(Image('analysis/gates.png',width=500,height=160))
    p('Слева - наблюдаемое время свежих прогонов с трейсингом и без; различия генерации ограничивают причинный вывод. Справа - число потерянных защищаемых задач. Статус учитывает и дополнительные условия REVIEW, поэтому не определяется только высотой столбца.',small)
    p(reviews['fix_note'],small)
    p('Пригодность порогов',heading)
    p(reviews['threshold_note'],small)
    p('Что можно воспроизвести',heading)
    p('eval.py --version <base|aa|candidate|fix> --runs 3 создаёт сводку и реальные трейсы. gate.py base.json candidate.json --report report.html сравнивает данные без модели. Дашборды A/A, изменения и исправления лежат в analysis/dashboards. В них есть манифесты, метрики, списки задач и ссылки на трейсы; отчёты CI и коды выхода - в analysis/ci_logs.',small)
    p('На ноутбуке prepare_laptop.py восстанавливает настоящие деревья спанов из native_traces через публичный API MLflow, сохраняя порядок, входы, выходы, статусы, токены и длительности. Проверка восстановления выполнена в отдельной базе без повторного вызова модели. UI: http://127.0.0.1:5006, эксперимент lr7, вкладка Traces. Локальные дашборды после восстановления открываются через dashboard.local.html.',small)
    p('Вывод',heading);p(reviews['conclusion'],small)
    p('Ограничения: один A/A-сравнительный запуск не оценивает надёжно частоту ложных тревог. Стенд может ошибаться в содержательной оценке (ЛР5). Предварительный технический запуск с ошибкой сериализации фиксированных дат сохранён отдельно; после исправления и теста записи объектов все условия измерены заново с одним протоколом. Пороги гейта не подбирались по результатам. Кодогенерация: Codex.',small)
    p('Источники: задание ЛР7; MLflow 3.18.0 (публичный Python API и локальная документация tracing); AgentDojo v1.2.2; OpenTelemetry Traces и GenAI semantic conventions; GitHub Actions; SRE, Monitoring Distributed Systems.',small)
    def footer(canvas,doc):canvas.setFont('Arial',8);canvas.drawString(45,23,'ЛР7 | Трейсинг и регрессионный гейт');canvas.drawRightString(550,23,str(doc.page))
    SimpleDocTemplate('report.pdf',pagesize=(595.28,841.89),leftMargin=45,rightMargin=45,topMargin=30,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
    import pypdfium2
    pdf=pypdfium2.PdfDocument('report.pdf');assert len(pdf)==4,len(pdf);Path('analysis/preview').mkdir(exist_ok=True)
    for i,page in enumerate(pdf,1):page.render(scale=1.4).to_pil().save(f'analysis/preview/{i}.png')
    print('Report:',len(pdf),'pages')
if __name__=='__main__':main()
