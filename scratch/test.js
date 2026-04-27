const nodemailer = require('nodemailer');
const transporter = nodemailer.createTransport({
  host: "smtp.example.com"
});

const sendEmail = () => {
  transporter.sendMail();
}

const userSchema = new mongoose.Schema({
  email: String
});

userSchema.pre('save', async function(next) {
  const hash = await bcrypt.hash(this.password, 10);
  this.password = hash;
  next();
});
