interface BookSideProps {
  title: string;
  rows: Array<[price: string, volume: number]>;
  side: "buy" | "sell";
}

import { memo } from "react";

export const BookSide = memo(function BookSide({ title, rows, side }: BookSideProps) {
  return (
    <section>
      <h3>{title}</h3>
      {rows.map(([price, volume]) => (
        <div className={`book-row ${side}`} key={`${side}-${price}`}>
          <span>{price}</span>
          <span>{volume.toLocaleString("en-US")}</span>
        </div>
      ))}
    </section>
  );
});
