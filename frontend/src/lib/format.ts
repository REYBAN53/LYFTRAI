const timeFormatter = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const numberFormatter = new Intl.NumberFormat();

export const formatTime = (date: Date) => timeFormatter.format(date);
export const formatNumber = (value: number) => numberFormatter.format(value);
