package com.showcase.dataanalysis.service;

import com.showcase.dataanalysis.dto.AnalyzeRequest;
import com.showcase.dataanalysis.dto.AnalyzeResponse;
import com.showcase.dataanalysis.dto.GroupStat;
import com.showcase.dataanalysis.dto.TopRow;
import org.springframework.stereotype.Service;
import tech.tablesaw.api.LongColumn;
import tech.tablesaw.api.Row;
import tech.tablesaw.api.StringColumn;
import tech.tablesaw.api.Table;
import tech.tablesaw.aggregate.AggregateFunctions;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

/**
 * 数据分析：数据集是"行号 i 的纯函数"，五种语言逐位一致：
 *   amount(i)  = (LCG(i+1) >> 32) % 100000
 *   category(i)= i % categories
 * 分位数统一 nearest-rank 口径（排序后取 ceil(p*n/100)-1 下标），
 * 原因：各库 quantile 默认插值方式不一（pandas=linear 等），放任默认值必然对不齐。
 */
@Service
public class AnalyzeService {

    private static final long MULT = 6364136223846793005L;
    private static final long INC = 1442695040888963407L;
    private static final long AMOUNT_MOD = 100_000L;

    private static long amountOf(long i) {
        long h = (i + 1) * MULT + INC; // long 溢出 = uint64 环绕，与其它语言一致
        return (h >>> 32) % AMOUNT_MOD;
    }

    private static long nearestRank(long[] sorted, int p) {
        int n = sorted.length;
        int idx = (p * n + 99) / 100; // ceil(p*n/100)
        idx = Math.max(1, Math.min(n, idx));
        return sorted[idx - 1];
    }

    public AnalyzeResponse analyze(AnalyzeRequest req) {
        int rows = req.effectiveRows();
        int cats = req.effectiveCategories();
        if (rows < 1_000 || rows > 2_000_000) {
            throw new IllegalArgumentException("rows must be in [1000, 2000000]");
        }
        if (cats < 1 || cats > 64) {
            throw new IllegalArgumentException("categories must be in [1, 64]");
        }

        long t0 = System.nanoTime();

        // ---- 数据生成（同时保留原始数组，供分位数/TopK 手写部分使用）----
        long[] ids = new long[rows];
        int[] catIdx = new int[rows];
        long[] amounts = new long[rows];
        LongColumn idCol = LongColumn.create("id");
        StringColumn catCol = StringColumn.create("category");
        LongColumn amountCol = LongColumn.create("amount");
        for (int i = 0; i < rows; i++) {
            long amount = amountOf(i);
            ids[i] = i;
            catIdx[i] = i % cats;
            amounts[i] = amount;
            idCol.append(i);
            catCol.append("cat-" + catIdx[i]);
            amountCol.append(amount);
        }
        Table sales = Table.create("sales", idCol, catCol, amountCol);

        long t1 = System.nanoTime();

        // ---- 分组聚合：tablesaw 一行流（Java 生态里的 DataFrame）----
        Table agg = sales.summarize("amount", AggregateFunctions.count, AggregateFunctions.sum)
                .by("category");
        List<String> aggCols = agg.columnNames();
        String cntCol = aggCols.stream().filter(c -> c.toLowerCase().contains("count"))
                .findFirst().orElseThrow();
        String sumCol = aggCols.stream()
                .filter(c -> c.toLowerCase().contains("sum") && !c.toLowerCase().contains("count"))
                .findFirst().orElseThrow();

        List<GroupStat> groups = new ArrayList<>();
        for (Row r : agg) {
            String cat = r.getString("category");
            int c = Integer.parseInt(cat.substring("cat-".length()));
            long count = (long) r.getDouble(cntCol);
            long sum = (long) r.getDouble(sumCol);
            // 分位数按统一 nearest-rank 手写（tablesaw 的 median 对偶数长度取中间均值，口径不同）
            long[] vals = amountsOfCategory(amounts, catIdx, c, (int) count);
            Arrays.sort(vals);
            groups.add(new GroupStat(cat, count, sum, (double) sum / (double) count,
                    nearestRank(vals, 50), nearestRank(vals, 95)));
        }
        groups.sort(Comparator.comparing(GroupStat::getCategory));

        // ---- Top-10：amount 降序，id 升序（手写；tablesaw 没有开箱即用的多键 TopK）----
        Integer[] order = new Integer[rows];
        for (int i = 0; i < rows; i++) {
            order[i] = i;
        }
        Arrays.sort(order, (a, b) -> {
            int cmp = Long.compare(amounts[b], amounts[a]);
            return cmp != 0 ? cmp : Long.compare(ids[a], ids[b]);
        });
        List<TopRow> top10 = new ArrayList<>();
        for (int i = 0; i < Math.min(10, rows); i++) {
            int idx = order[i];
            top10.add(new TopRow(ids[idx], "cat-" + catIdx[idx], amounts[idx]));
        }

        long t2 = System.nanoTime();
        return new AnalyzeResponse(rows, cats, groups, top10,
                (t1 - t0) / 1_000_000, (t2 - t1) / 1_000_000, (t2 - t0) / 1_000_000);
    }

    private static long[] amountsOfCategory(long[] amounts, int[] catIdx, int c, int expected) {
        long[] out = new long[expected];
        int k = 0;
        for (int i = 0; i < amounts.length; i++) {
            if (catIdx[i] == c) {
                out[k++] = amounts[i];
            }
        }
        return Arrays.copyOf(out, k);
    }
}
