FROM python:3.13

WORKDIR /app

COPY . .

RUN make install

EXPOSE 8080

CMD ["make", "serve"]
