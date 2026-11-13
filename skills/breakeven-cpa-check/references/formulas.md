# Formulas

## Break-even CPA

The most that one order can cost in advertising before it loses money:

    break-even CPA = price
                     - product cost
                     - shipping cost
                     - price x payment fee %
                     - fixed payment fee
                     - other per-order costs

Worked example with placeholder numbers:

| Item | Amount |
|---|---:|
| Price | 60.00 |
| Product cost | -20.00 |
| Shipping | -5.00 |
| Payment fee 3% | -1.80 |
| Fixed fee | -0.30 |
| Packaging | -2.00 |
| **Break-even CPA** | **30.90** |

Use prices and costs on the same tax basis (all net of VAT, or all gross).

## Break-even ROAS

    break-even ROAS = price / break-even CPA

With the numbers above: 60.00 / 30.90 = 1.94. Any ad below that ROAS loses
money on the first order.

## Cut threshold

    cut threshold = multiplier x break-even CPA

With a multiplier of 2.5: 77.25. An ad that reaches 77.25 in spend with zero
adds to cart and zero purchases is cut.

Why 2-3x and not 1x: at a spend equal to one break-even CPA, an ad that
converts exactly at break-even still has roughly a one-in-three chance of
showing no purchase by pure chance. By 2.5x that chance is under one in ten,
and the absence of even an add to cart makes a late recovery unlikely.

## From the command line

    ad-library-insights breakeven --price 60 --product-cost 20 --shipping-cost 5 \
        --fee-pct 3 --fee-fixed 0.30 --other-costs 2 --multiplier 2.5 --csv export.csv
