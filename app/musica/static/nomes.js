// "Seu nome" (quem dá o presente) igual ao de quem recebe — o comprador pôs o nome dela ali e o presente saía
// "de Rose para Rose" (docs/MUSICA.md, o quiz). Usado no quiz e na área da compra, que avisam uma vez e seguem no
// segundo toque (às vezes os nomes são iguais mesmo).
// Igual: o nome inteiro (sem acento, maiúscula nem espaço a mais) ou, se "Seu nome" é uma palavra só, a 1ª palavra de
// quem recebe ("Rose" × "Rose Maria"). "Maria Helena" × "Maria Clara" não é igual.
window.MesmoNome = (function () {
  const limpar = n => (n || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim().split(/\s+/).filter(Boolean);
  return function (de, ...nomes) {
    const d = limpar(de);
    if (!d.length) return false;
    return nomes.some(n => {
      const r = limpar(n);
      return r.length && (d.join(" ") === r.join(" ") || (d.length === 1 && d[0] === r[0]));
    });
  };
})();
